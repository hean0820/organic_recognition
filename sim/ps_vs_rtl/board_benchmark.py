"""Same-board PS software versus the existing complete RTL CNN API.
Run in the existing application Notebook: run(app). No new hardware owner.
"""
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
from software import ROOT,SoftwareCnn,checked_manifest,sha,validate_software


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def clocks():
    # Match app.bootstrap.ensure_overlay; PYNQ's global Zynq Clocks uses
    # a 50MHz default reference, while this verified board uses 33.333333MHz.
    from pynq.ps import _ClocksZynq
    reader=_ClocksZynq(ref_clk_mhz=33.333333)
    return {'cpu_mhz':float(reader.get_cpu_mhz()),
            'fclk0_mhz':float(reader.get_pl_clk(0)),
            'fclk1_mhz':float(reader.get_pl_clk(1))}


def environment():
    result=dict(platform=platform.platform(),machine=platform.machine(),python=sys.version,
                clocks_mhz=clocks(),logical_cpu_count=os.cpu_count(),load_average=list(os.getloadavg()))
    if hasattr(os,'sched_getaffinity'): result['cpu_affinity']=sorted(os.sched_getaffinity(0))
    for path,key in [('/proc/cpuinfo','cpuinfo'),
            ('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor','cpu0_governor'),
            ('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq','cpu0_frequency_khz')]:
        try: result[key]=Path(path).read_text().strip()
        except OSError: result[key]=None
    return result


def stats(values):
    a=np.asarray(values,dtype=np.float64)
    if a.ndim!=1 or not len(a) or not np.all(np.isfinite(a)) or np.any(a<=0):
        raise ValueError('Invalid timing records')
    return dict(count=len(a),mean_ms=float(a.mean()),median_ms=float(np.median(a)),
                p95_ms=float(np.percentile(a,95)),min_ms=float(a.min()),max_ms=float(a.max()))


def summarize(records):
    if not records or any(not r['exact_logits_match'] for r in records):
        raise ValueError('Cannot summarize missing or numerically inconsistent measurements')
    cpu=stats([r['ps_software_wall_ms'] for r in records])
    rtl=stats([r['rtl_call_wall_ms'] for r in records])
    ratio=cpu['mean_ms']/rtl['mean_ms']
    return dict(ps_software=cpu,rtl_call=rtl,speedup_ratio_of_means=ratio,
                latency_reduction_percent=100*(1-rtl['mean_ms']/cpu['mean_ms']),
                measured_pairs=len(records),all_22_logits_exact=True)


def verify_application(app,manifest):
    if platform.system()!='Linux' or platform.machine().lower() not in ('armv7l','armv7'):
        raise RuntimeError('Board timing requires the real Zynq ARMv7 Linux application; host timing is not accepted')
    import pynq
    if not isinstance(app.cnn,pynq.MMIO) or not app.cnn.device.has_capability('MEMORY_MAPPED'):
        raise RuntimeError('Expected existing local PYNQ MMIO owner')
    if app.cnn.base_addr!=0x43c00000 or app.cnn.length!=0x10000:
        raise RuntimeError('CNN MMIO contract differs')
    if app.cnn_io.backend!='NATIVE_C_VOLATILE_U32': raise RuntimeError('Unexpected transfer backend')
    folder=Path(app.folder)
    for name,digest in manifest['runtime_sha256'].items():
        if sha(folder/name)!=digest: raise RuntimeError('Runtime/model mismatch: '+name)
    app._check();app.unified.verify_identity()
    if app.requests.status()['active'] or (app.voice_worker and app.voice_worker.is_alive()):
        raise RuntimeError('Finish the active camera/voice request before benchmarking')
    if app.audio is not None and app.audio.owns_capture:
        raise RuntimeError('Finish the active audio recording before benchmarking')
    if not app.unified.model_ready: raise RuntimeError('Existing CNN model not ready')
    observed=clocks()
    if abs(observed['fclk0_mhz']-100)>0.1 or abs(observed['fclk1_mhz']-100)>0.1:
        raise RuntimeError('Expected 100/100MHz with 33.333333MHz reference; observed: '+repr(observed))


def make_report_text(report):
    s=report['summary'];cpu=s['ps_software']['mean_ms'];rtl=s['rtl_call']['mean_ms']
    count=report['performance_input_count'];rounds=report['rounds']
    title='PS纯软件与RTL加速的同板推理对比'
    text='# '+title+'\n\n'
    text+='| 指标 | PS纯软件C推理 | PL统一RTL加速调用 |\n|---|---:|---:|\n'
    text+='| 单张平均推理耗时 | %.3f ms | %.3f ms |\n'%(cpu,rtl)
    text+='| 中位数 / P95 | %.3f / %.3f ms | %.3f / %.3f ms |\n'%(s['ps_software']['median_ms'],s['ps_software']['p95_ms'],s['rtl_call']['median_ms'],s['rtl_call']['p95_ms'])
    text+='| 相对软件加速比 | 1× | %.2f× |\n'%s['speedup_ratio_of_means']
    text+='| 推理耗时降低 | — | %.2f%% |\n'%s['latency_reduction_percent']
    text+='| 22维整数输出 | 冻结整数参考 | 所有计时样本逐值一致 |\n\n'
    text+=('在同一块Zynq-7020上，使用相同的定点模型、参数和%d张冻结开发验证输入（每类2张），'
           '预热%d次后，交替顺序重复%d轮，共%d组配对测量。PS软件采用GCC -O3单线程C实现，'
           'RTL调用包含输入写入及读回校验、启动、等待、22维输出读取和ACK。'
           '两者均排除摄像、预处理、显示、模型初始化和文件读写。\n\n')%(count,report['warmup_pairs'],rounds,s['measured_pairs'])
    text+=('本次实测平均推理耗时由%.3f ms变为%.3f ms，加速比为%.2f倍，耗时降低%.2f%%。'
           '结果仅对应以上测试配置；44张固定输入用于计时与一致性回归，不是新的独立准确率评估。'
           '不将其倒推为摄像端到端FPS或交互响应时间。\n')%(cpu,rtl,s['speedup_ratio_of_means'],s['latency_reduction_percent'])
    return text


def run(app,rounds=3,warmup=5):
    """44 real inputs x 3 rounds, alternating order; keeps current session alive."""
    if isinstance(rounds,bool) or not isinstance(rounds,int) or not 3<=rounds<=20:
        raise ValueError('rounds must be an integer from 3 to 20')
    if isinstance(warmup,bool) or not isinstance(warmup,int) or not 5<=warmup<=100:
        raise ValueError('warmup must be an integer from 5 to 100')
    manifest=checked_manifest()
    # Reject a PC or incompatible runtime before compiling or taking app locks.
    verify_application(app,manifest)
    folder=ROOT/'results'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False)
    path=folder/'board_result.json'
    report=dict(passed=False,hardware_accessed=False,started_at=stamp(),rounds=rounds,
                warmup_pairs=warmup,model_sha256=manifest['model_sha256'],records=[],
                benchmark_manifest_sha256=sha(ROOT/'manifest.json'),
                report_directory=str(folder),
                board_realtime_clock_verified=False,
                timing_clock='time.perf_counter; independent of board calendar time',
                measurement='batch1 complete inference API wall time, same ARMv7 board',
                baseline='newly reconstructed CPU C integer baseline, not a historical deployed version',
                excludes='camera, preprocessing, UI/3D, model loading, compilation, disk IO',
                rtl_includes='identity/idle checks, input write/readback, START, wait, logits, ACK, status',
                app_state_policy='app/request locks held; PS preview redraw pauses; camera/HDMI DMA stays active')
    try:
        with SoftwareCnn() as cpu:
            report['build']=cpu.build
            # Locks prevent camera/host/voice inference and redraw from interleaving.
            with app.lock,app.requests.lock:
                verify_application(app,manifest)
                before=app.requests.status();memory_before=app.memory.status()
                report['environment_before']=environment()
                print('PS_RTL_BENCHMARK_RUNNING: preview redraw pauses; keep this kernel open',flush=True)
                report['cpu_correctness']=validate_software(cpu)
                with np.load(ROOT/'assets/vectors.npz',allow_pickle=False) as data:
                    images=data['inputs'].copy();expected=data['logits'].copy()
                indices=[i for i,c in enumerate(manifest['cases']) if c['kind']=='validation']
                if len(indices)!=44 or sorted(set(manifest['cases'][i]['true_class'] for i in indices))!=list(range(22)):
                    raise RuntimeError('Expected exactly two validation inputs per each of 22 classes')
                report['performance_input_count']=len(indices)

                def paired(index,cpu_first):
                    image=images[index];reference=expected[index]
                    outputs={};measure={}
                    for backend in (('cpu','rtl') if cpu_first else ('rtl','cpu')):
                        t=time.perf_counter()
                        if backend=='cpu':
                            outputs['cpu']=cpu.infer(image)
                            measure['ps_software_wall_ms']=(time.perf_counter()-t)*1000
                        else:
                            report['hardware_accessed']=True
                            try:
                                result=app.unified.infer(image,app.cnn_io,diagnostics=False)
                            except BaseException as original:
                                # KeyboardInterrupt is not handled by the production
                                # driver's Exception branch. Drain before releasing
                                # the app lock, retaining its existing BO owner.
                                if app.unified.dma_owned:
                                    try: app.unified.recover()
                                    except BaseException as recovery:
                                        app.stop_event.set()
                                        raise RuntimeError('CNN recovery incomplete; keep this kernel/session and model buffers: '+repr(recovery)) from original
                                raise
                            measure['rtl_call_wall_ms']=(time.perf_counter()-t)*1000
                            outputs['rtl']=result['_diagnostic_arrays']['logits']
                            measure['rtl_cycles']=int(result['hardware']['cycles'])
                            measure['rtl_sequence']=int(result['hardware']['sequence'])
                    if not np.array_equal(outputs['cpu'],reference) or not np.array_equal(outputs['rtl'],reference):
                        raise AssertionError('PS/RTL/reference logits differ at '+manifest['cases'][index]['name'])
                    measure.update(case=manifest['cases'][index]['name'],case_index=index,
                                   order='CPU_THEN_RTL' if cpu_first else 'RTL_THEN_CPU',exact_logits_match=True,
                                   logits=[int(x) for x in outputs['rtl']])
                    return measure

                for i in range(warmup): paired(indices[i%len(indices)],i%2==0)
                print('WARMUP_COMPLETE',warmup,'pairs',flush=True)
                for r in range(rounds):
                    for position,index in enumerate(indices):
                        record=paired(index,(r+position)%2==0);record['round']=r+1
                        report['records'].append(record)
                        if (position+1)%11==0: print('MEASURED_PAIRS',len(report['records']),'/',rounds*len(indices),flush=True)
                    print('MEASURED_ROUND_COMPLETE',r+1,'/',rounds,flush=True)
                if app.requests.status()!=before: raise RuntimeError('Application selection/request changed')
                if app.memory.status()!=memory_before: raise RuntimeError('DMA memory ownership changed')
                app._check()
                report['environment_after']=environment()
                if any(abs(report['environment_before']['clocks_mhz'][k]-report['environment_after']['clocks_mhz'][k])>0.1
                       for k in report['environment_before']['clocks_mhz']):
                    raise RuntimeError('Clock configuration changed during measurement')
                report.update(summary=summarize(report['records']),request_unchanged=True,memory_unchanged=True,passed=True)
    except BaseException as error:
        report.update(passed=False,error=repr(error));raise
    finally:
        report['finished_at']=stamp()
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('BENCHMARK_REPORT',str(path),flush=True)
    text=make_report_text(report)
    (folder/'对比表与报告段落.md').write_text(text,encoding='utf-8')
    print(text,flush=True)
    return report
