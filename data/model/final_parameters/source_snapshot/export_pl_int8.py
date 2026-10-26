"""Export a trained OrganicCNN as a documented INT8 package for the PL team."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from organic_torch_model import AUXILIARY_WEIGHT, CONFUSION_GROUPS, OrganicCNN


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "organic_data"
Q_BITS = 30
# 当前部署网络只保留两层卷积（2026-10-04 移除 Conv3）。
# 该常量同时被参数导出、Golden 导出和文档化元数据引用，禁止散落魔数。
NUM_CONV_LAYERS = 2


def fuse_conv_bn(conv, bn):
    weight = conv.weight.detach().cpu().double()
    bias = (conv.bias.detach().cpu().double() if conv.bias is not None
            else torch.zeros(weight.shape[0], dtype=torch.float64))
    scale = bn.weight.detach().cpu().double() / torch.sqrt(
        bn.running_var.detach().cpu().double() + bn.eps
    )
    fused_weight = weight * scale[:, None, None, None]
    fused_bias = bn.bias.detach().cpu().double() + (
        bias - bn.running_mean.detach().cpu().double()
    ) * scale
    return fused_weight.float(), fused_bias.float()


def fuse_classifier(model):
    weight = model.classifier.weight.detach().cpu().clone()
    bias = model.classifier.bias.detach().cpu().clone()
    for group_name, indices in CONFUSION_GROUPS.items():
        head = model.group_heads[group_name]
        for local_index, class_index in enumerate(indices):
            weight[class_index] += AUXILIARY_WEIGHT * head.weight[local_index].detach().cpu()
            bias[class_index] += AUXILIARY_WEIGHT * head.bias[local_index].detach().cpu()
    return weight, bias


def fused_forward(x, params, return_activations=False):
    """按当前 NUM_CONV_LAYERS 层执行卷积+ReLU+MaxPool，顺序与 PL 数据通路一致。"""
    activations = {}
    for layer_index in range(1, NUM_CONV_LAYERS + 1):
        weight, bias = params[f"conv{layer_index}"]
        x = F.conv2d(x, weight.to(x.device), bias.to(x.device), padding=1)
        x = F.relu(x)
        activations[f"conv{layer_index}_relu"] = x
        x = F.max_pool2d(x, 2)
    x = torch.flatten(x, 1)
    weight, bias = params["fc1"]
    x = F.relu(F.linear(x, weight.to(x.device), bias.to(x.device)))
    activations["fc1_relu"] = x
    weight, bias = params["fc2"]
    logits = F.linear(x, weight.to(x.device), bias.to(x.device))
    return (logits, activations) if return_activations else logits


def symmetric_int8(tensor):
    maximum = float(tensor.abs().max())
    scale = maximum / 127.0 if maximum else 1.0
    quantized = torch.clamp(torch.round(tensor / scale), -127, 127).to(torch.int8)
    return quantized, scale


def q30_multiplier(real_multiplier):
    value = int(round(real_multiplier * (1 << Q_BITS)))
    if not 0 <= value <= np.iinfo(np.int32).max:
        raise ValueError(f"Q30 multiplier out of INT32 range: {real_multiplier} -> {value}")
    return value


def write_parameter_files(base_path, array):
    array = np.ascontiguousarray(array)
    if array.dtype == np.int8:
        raw = array
        unsigned = array.view(np.uint8).reshape(-1)
        width = 2
    elif array.dtype == np.int32:
        raw = array.astype("<i4", copy=False)
        unsigned = raw.view("<u4").reshape(-1)
        width = 8
    else:
        raise TypeError(f"Unsupported export dtype: {array.dtype}")
    raw.tofile(base_path.with_suffix(".bin"))
    hex_values = [f"{int(value):0{width}X}" for value in unsigned]
    base_path.with_suffix(".hex").write_text("\n".join(hex_values) + "\n", encoding="ascii")
    coe = "memory_initialization_radix=16;\nmemory_initialization_vector=\n"
    coe += ",\n".join(hex_values) + ";\n"
    base_path.with_suffix(".coe").write_text(coe, encoding="ascii")


def quantize_params(float_params, activation_scales):
    """按层输入/输出 scale 量化权重与偏置，并计算 Q30 requant 乘数。"""
    quantized = {}
    # 每个卷积层的输入来自上一层的 ReLU 激活；fc2 输入来自 fc1 的 ReLU 激活。
    layer_input_scales = {
        "conv1": 1.0 / 255.0,
        "conv2": activation_scales["conv1_relu"],
        "fc1": activation_scales[f"conv{NUM_CONV_LAYERS}_relu"],
        "fc2": activation_scales["fc1_relu"],
    }
    layer_output_scales = {
        f"conv{index}": activation_scales[f"conv{index}_relu"]
        for index in range(1, NUM_CONV_LAYERS + 1)
    }
    layer_output_scales["fc1"] = activation_scales["fc1_relu"]
    metadata = {}
    for name, (weight, bias) in float_params.items():
        q_weight, weight_scale = symmetric_int8(weight)
        input_scale = layer_input_scales[name]
        q_bias = torch.round(bias / (input_scale * weight_scale)).to(torch.int32)
        quantized[name] = (q_weight, q_bias)
        entry = {
            "input_scale": input_scale,
            "weight_scale": weight_scale,
            "bias_scale": input_scale * weight_scale,
            "weight_shape": list(weight.shape),
            "bias_shape": list(bias.shape),
        }
        if name != "fc2":
            output_scale = layer_output_scales[name]
            multiplier = input_scale * weight_scale / output_scale
            entry.update({
                "output_scale": output_scale,
                "requant_real_multiplier": multiplier,
                "requant_multiplier_q30": q30_multiplier(multiplier),
                "requant_right_shift": Q_BITS,
                "output_min": 0,
                "output_max": 127,
            })
        else:
            entry["logit_scale"] = input_scale * weight_scale
        metadata[name] = entry
    return quantized, metadata


def quantized_forward_fast(x, quantized, metadata):
    # Float tensors hold integer values here. Rounding/clamping emulate the integer datapath.
    x = torch.round(x * 255.0).clamp(0, 255)
    for layer_index in range(1, NUM_CONV_LAYERS + 1):
        name = f"conv{layer_index}"
        weight, bias = quantized[name]
        acc = F.conv2d(x, weight.to(x.device).float(), bias.to(x.device).float(), padding=1)
        multiplier = metadata[name]["requant_multiplier_q30"] / float(1 << Q_BITS)
        x = torch.round(acc * multiplier).clamp(0, 127)
        x = F.max_pool2d(x, 2)
    x = torch.flatten(x, 1)
    weight, bias = quantized["fc1"]
    acc = F.linear(x, weight.to(x.device).float(), bias.to(x.device).float())
    multiplier = metadata["fc1"]["requant_multiplier_q30"] / float(1 << Q_BITS)
    x = torch.round(acc * multiplier).clamp(0, 127)
    weight, bias = quantized["fc2"]
    return torch.round(F.linear(x, weight.to(x.device).float(), bias.to(x.device).float())).to(torch.int32)


def rounded_q30(acc, multiplier):
    acc = acc.to(torch.int64)
    product = acc * int(multiplier)
    half = 1 << (Q_BITS - 1)
    return torch.where(product >= 0, (product + half) >> Q_BITS,
                       -(((-product) + half) >> Q_BITS))


def quantized_forward_exact(x_uint8, quantized, metadata):
    """逐层保存 INT32/INT8 参考结果，作为 PL 逐层对拍的 Golden 数据源。"""
    layers = {"input_uint8": x_uint8.cpu().numpy().astype(np.uint8)}
    x = x_uint8.to(torch.float64)
    for layer_index in range(1, NUM_CONV_LAYERS + 1):
        name = f"conv{layer_index}"
        weight, bias = quantized[name]
        acc = torch.round(F.conv2d(x, weight.double(), bias.double(), padding=1)).to(torch.int64)
        layers[f"{name}_acc_int32"] = acc.cpu().numpy().astype(np.int32)
        x_int = rounded_q30(acc, metadata[name]["requant_multiplier_q30"]).clamp(0, 127)
        layers[f"{name}_relu_int8"] = x_int.cpu().numpy().astype(np.int8)
        x = F.max_pool2d(x_int.double(), 2)
        layers[f"pool{layer_index}_int8"] = x.cpu().numpy().astype(np.int8)
    x = torch.flatten(x, 1)
    weight, bias = quantized["fc1"]
    acc = torch.round(F.linear(x, weight.double(), bias.double())).to(torch.int64)
    layers["fc1_acc_int32"] = acc.cpu().numpy().astype(np.int32)
    x_int = rounded_q30(acc, metadata["fc1"]["requant_multiplier_q30"]).clamp(0, 127)
    layers["fc1_relu_int8"] = x_int.cpu().numpy().astype(np.int8)
    weight, bias = quantized["fc2"]
    logits = torch.round(F.linear(x_int.double(), weight.double(), bias.double())).to(torch.int32)
    layers["fc2_logits_int32"] = logits.cpu().numpy().astype(np.int32)
    return logits, layers


def load_validation(dataset_name):
    paths = {
        "original": DATA / "val.npz",
        "dataset1": DATA / "val_dataset1.npz",
        "original_photos": DATA / "original_photos_dataset" / "val_original_photos.npz",
    }
    data = np.load(paths[dataset_name])
    return torch.from_numpy(data["x"]).float(), torch.from_numpy(data["y"]).long()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", nargs="?", default=str(DATA / "result_6" / "organic_best.pt"))
    parser.add_argument("--golden-count", type=int, default=20)
    args = parser.parse_args()
    checkpoint_path = Path(args.checkpoint).resolve()
    output_dir = checkpoint_path.parent / "pl_export_int8"
    output_dir.mkdir(exist_ok=False)
    golden_dir = output_dir / "golden"
    golden_dir.mkdir()

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    names = checkpoint["class_names"]
    model = OrganicCNN(len(names))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    # 按当前 NUM_CONV_LAYERS 收集参数；不再硬编码 features 下标，
    # 避免层数变化后 Conv/BN 配对错位导致静默的融合错误。
    features = list(model.features)
    float_params = {
        f"conv{layer_index}": fuse_conv_bn(features[4 * (layer_index - 1)], features[4 * (layer_index - 1) + 1])
        for layer_index in range(1, NUM_CONV_LAYERS + 1)
    }
    float_params["fc1"] = (model.embedding[1].weight.detach().cpu(), model.embedding[1].bias.detach().cpu())
    float_params["fc2"] = fuse_classifier(model)
    x, y = load_validation(checkpoint.get("dataset_name", "original_photos"))
    with torch.inference_mode():
        original = model(x[:16])
        fused = fused_forward(x[:16], float_params)
    fusion_error = float((original - fused).abs().max())
    if fusion_error > 1e-4:
        raise RuntimeError(f"Fusion verification failed: max error {fusion_error}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # 只标定实际存在的层，避免留下 conv3 等已移除层的空统计。
    maxima = {
        **{f"conv{layer_index}_relu": 0.0 for layer_index in range(1, NUM_CONV_LAYERS + 1)},
        "fc1_relu": 0.0,
    }
    with torch.inference_mode():
        for start in range(0, len(x), 64):
            _, activations = fused_forward(x[start:start + 64].to(device), float_params, True)
            for name, value in activations.items():
                maxima[name] = max(maxima[name], float(value.max()))
    activation_scales = {name: maximum / 127.0 if maximum else 1.0
                         for name, maximum in maxima.items()}
    quantized, quant_metadata = quantize_params(float_params, activation_scales)

    predictions = []
    with torch.inference_mode():
        for start in range(0, len(x), 128):
            logits = quantized_forward_fast(x[start:start + 128].to(device), quantized, quant_metadata)
            predictions.append(logits.argmax(1).cpu())
    predictions = torch.cat(predictions)
    int8_accuracy = float((predictions == y).float().mean())

    tensors = {}
    for layer_name, (weight, bias) in quantized.items():
        weight_array = weight.numpy().astype(np.int8)
        bias_array = bias.numpy().astype(np.int32)
        tensors[f"{layer_name}_weight"] = {
            "dtype": "int8", "shape": list(weight_array.shape),
            "order": "OC_IC_KY_KX" if layer_name.startswith("conv") else "OUT_IN",
        }
        tensors[f"{layer_name}_bias"] = {
            "dtype": "int32", "shape": list(bias_array.shape), "order": "OUT",
        }
        write_parameter_files(output_dir / f"{layer_name}_weight_int8", weight_array)
        write_parameter_files(output_dir / f"{layer_name}_bias_int32", bias_array)

    golden_count = min(args.golden_count, len(x))
    golden_index = np.linspace(0, len(x) - 1, golden_count, dtype=int)
    golden_summary = []
    for sequence, index in enumerate(golden_index):
        input_uint8 = torch.round(x[index:index + 1] * 255.0).clamp(0, 255).to(torch.uint8)
        logits, layers = quantized_forward_exact(input_uint8, quantized, quant_metadata)
        stem = f"sample_{sequence:03d}"
        input_uint8.numpy().reshape(-1).tofile(golden_dir / f"{stem}_input_uint8.bin")
        logits.numpy().astype("<i4").reshape(-1).tofile(golden_dir / f"{stem}_logits_int32.bin")
        np.savez_compressed(golden_dir / f"{stem}_layers.npz", **layers)
        golden_summary.append({
            "sample": stem, "validation_index": int(index), "expected_class": int(y[index]),
            "predicted_class": int(logits.argmax(1)), "expected_name": names[int(y[index])],
            "predicted_name": names[int(logits.argmax(1))],
        })

    manifest = {
        "format_version": 1,
        "source_checkpoint": str(checkpoint_path),
        "source_validation_accuracy": float(checkpoint["val_acc"]),
        "int8_reference_accuracy": int8_accuracy,
        "fusion_max_abs_error": fusion_error,
        "classes": len(names),
        "class_names": names,
        "input": {"shape": [1, 64, 64], "dtype": "uint8", "order": "CHW_ROW_MAJOR",
                  "scale": 1.0 / 255.0, "zero_point": 0},
        "weights": {"dtype": "int8", "range": [-127, 127], "zero_point": 0},
        "bias": {"dtype": "int32", "endianness": "little"},
        "accumulator": {"dtype": "int32"},
        "activation": {"dtype": "int8", "range_after_relu": [0, 127], "zero_point": 0},
        "requantization": {"formula": "round_away_from_zero(acc * multiplier_q30 / 2^30)",
                           "right_shift": Q_BITS, "overflow": "saturate", "relu_then_range": [0, 127]},
        "conv": {"kernel": [3, 3], "stride": 1, "padding": 1, "padding_value": 0,
                 "weight_order": "OC_IC_KY_KX"},
        "pool": {"type": "max", "kernel": [2, 2], "stride": 2, "padding": 0},
        "fc_weight_order": "OUT_IN",
        "binary_format": {"header": "none", "int32_endianness": "little", "signed": "twos_complement"},
        "tensors": tensors,
        "layers": quant_metadata,
        "golden_samples": golden_summary,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_dir / "class_names.json").write_text(json.dumps(names, indent=2), encoding="ascii")
    report = (
        f"Source checkpoint: {checkpoint_path}\n"
        f"FP32 validation accuracy: {float(checkpoint['val_acc']):.4%}\n"
        f"INT8 reference accuracy: {int8_accuracy:.4%}\n"
        f"Accuracy change: {int8_accuracy - float(checkpoint['val_acc']):+.4%}\n"
        f"Fusion max absolute error: {fusion_error:.9g}\n"
        f"Golden samples: {golden_count}\n"
    )
    (output_dir / "export_report.txt").write_text(report, encoding="utf-8")
    print(report)
    print(f"Exported to: {output_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Export failed: {error}", file=sys.stderr)
        raise
