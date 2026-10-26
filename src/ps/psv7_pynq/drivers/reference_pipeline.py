"""Pure CPU references for the frozen PL filters and PS postprocessing."""
import zlib
import numpy as np

KERNEL = np.array([0,0,0,1,0,0,1,0,1,1,1,1,2,1,3,2,3,3,4,4,5,5,5,6,7,7,8,8,8,9,9,9,9,10,9,9,9,9,8,8,8,7,7,6,5,5,5,4,4,3,3,2,3,1,2,1,1,1,1,0,1,0,0,1,0,0,0], dtype=np.uint32)
CODES = ('OK', 'BLANK', 'EDGE', 'DARK', 'WEAK', 'BAD_ARGUMENT', 'ACCEL_ERROR')
REPORT_FIELDS = ('version code threshold components kept foreground_pixels bbox_x bbox_y bbox_w bbox_h '
                 'crop_x crop_y crop_w crop_h high_milli resized_w resized_h mean_gray detect_crc input_crc').split()


def reference_filters(frame):
    """Integer mirror of stage1/hls/prep_accel.cpp, including reflection/rounding."""
    if frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
        raise ValueError('Expected 720x1280x3 uint8 BGR frame')
    roi = frame[160:560, 160:1120].astype(np.uint32)
    mono = (1868*roi[:,:,0] + 9617*roi[:,:,1] + 4899*roi[:,:,2] + 8192) >> 14
    horizontal_small = np.empty((400, 640), dtype=np.uint32)
    horizontal_small[:,0::2] = 2*mono[:,0::3] + mono[:,1::3]
    horizontal_small[:,1::2] = mono[:,1::3] + 2*mono[:,2::3]
    detection = np.empty((267, 640), dtype=np.uint8)
    for y in range(267):
        y0, y1 = y*400, (y+1)*400
        total = np.zeros(640, dtype=np.uint32)
        for sy in range(y0//267, (y1+266)//267):
            weight = min(y1, (sy+1)*267) - max(y0, sy*267)
            total += horizontal_small[sy]*weight
        detection[y] = (total+600)//1200
    trimmed = detection[21:245, 51:588].astype(np.uint32)
    padded = np.pad(trimmed, 1, mode='reflect')
    total = np.zeros((224, 537), dtype=np.uint32)
    for dy, wy in enumerate((1, 2, 1)):
        for dx, wx in enumerate((1, 2, 1)):
            total += padded[dy:dy+224, dx:dx+537]*(wy*wx)
    gray = ((total+8) >> 4).astype(np.uint8)
    padded = np.pad(gray.astype(np.uint32), ((0,0),(33,33)), mode='reflect')
    horizontal = np.zeros((224,537), dtype=np.uint32)
    for k, weight in enumerate(KERNEL):
        if weight: horizontal += padded[:,k:k+537]*weight
    padded = np.pad(horizontal, ((33,33),(0,0)), mode='reflect')
    total = np.zeros((224,537), dtype=np.uint32)
    for k, weight in enumerate(KERNEL):
        if weight: total += padded[k:k+224]*weight
    background = ((total+32768) >> 16).astype(np.int32)
    ink = np.maximum(background-gray.astype(np.int32), 0).astype(np.uint8)
    return detection, gray, horizontal.astype(np.uint16), ink


def round_even(numerator, denominator):
    q, r = divmod(int(numerator), int(denominator))
    return q + int(r*2 > denominator or (r*2 == denominator and q & 1))


def quantile_milli(hist, n, per_mille):
    rank = (int(n)-1)*per_mille
    lo, hi = rank//1000, (rank+999)//1000
    cumulative = np.cumsum(hist)
    lv = int(np.searchsorted(cumulative, lo, side='right'))
    hv = int(np.searchsorted(cumulative, hi, side='right'))
    return lv*1000 + (hv-lv)*(rank % 1000)


def cubic(x):
    a = -0.75
    x = abs(x)
    if x <= 1.0: return ((a+2.0)*x-(a+3.0))*x*x+1.0
    if x < 2.0: return ((a*x-5.0*a)*x+8.0*a)*x-4.0*a
    return 0.0


def resize_canvas(crop, report):
    ch, cw = crop.shape
    side = max(cw, ch)
    rw, rh = max(1, round_even(cw*56, side)), max(1, round_even(ch*56, side))
    report['resized_w'], report['resized_h'] = rw, rh
    ox, oy = (64-rw)//2, (64-rh)//2
    out = np.zeros((64,64), dtype=np.uint8)
    for y in range(rh):
        for x in range(rw):
            if side >= 56:
                x0, x1, y0, y1 = x*cw, (x+1)*cw, y*ch, (y+1)*ch
                total = 0
                for sy in range(y0//rh, (y1+rh-1)//rh):
                    yl, yr = max(y0, sy*rh), min(y1, (sy+1)*rh)
                    for sx in range(x0//rw, (x1+rw-1)//rw):
                        xl, xr = max(x0, sx*rw), min(x1, (sx+1)*rw)
                        total += int(crop[sy,sx])*(yr-yl)*(xr-xl)
                value = (total+cw*ch//2)//(cw*ch)
            else:
                fx, fy = (x+0.5)*cw/rw-0.5, (y+0.5)*ch/rh-0.5
                ix, iy = int(np.floor(fx)), int(np.floor(fy))
                total = 0.0
                for dy in range(-1, 3):
                    for dx in range(-1, 3):
                        sx, sy = min(cw-1, max(0, ix+dx)), min(ch-1, max(0, iy+dy))
                        total += int(crop[sy,sx])*cubic(fx-ix-dx)*cubic(fy-iy-dy)
                value = 0 if total <= 0 else 255 if total >= 255 else int(total+0.5)
            out[oy+y, ox+x] = value
    return out


def postprocess(detection, gray, ink):
    """Exact port of stage1/vitis/ov5640_hdmi/src/preprocess.c."""
    if detection.shape != (267,640) or gray.shape != (224,537) or ink.shape != gray.shape:
        raise ValueError('Unexpected filtered shapes')
    if any(a.dtype != np.uint8 for a in (detection, gray, ink)):
        raise ValueError('Expected uint8 filters')
    r = {key: 0 for key in REPORT_FIELDS}
    r.update(version=0x10000, stage_us=[0]*6, total_us=0,
             detect_crc=zlib.crc32(detection.tobytes()), mean_gray=int(gray.sum())//gray.size)
    r['threshold'] = max(8, quantile_milli(np.bincount(ink.ravel(), minlength=256), ink.size, 985)//1000)
    foreground = ink >= r['threshold']
    visited = np.zeros_like(foreground)
    x0, y0, x1, y1 = 537, 224, 0, 0
    for p in np.flatnonzero(foreground):
        y, x = divmod(int(p), 537)
        if visited[y,x]: continue
        queue = [(y,x)]
        visited[y,x] = True
        r['components'] += 1
        cx0, cy0, cx1, cy1, head = 537, 224, 0, 0, 0
        while head < len(queue):
            y, x = queue[head]; head += 1
            cx0, cy0, cx1, cy1 = min(cx0,x), min(cy0,y), max(cx1,x), max(cy1,y)
            for ny in range(max(0,y-1), min(224,y+2)):
                for nx in range(max(0,x-1), min(537,x+2)):
                    if foreground[ny,nx] and not visited[ny,nx]:
                        visited[ny,nx] = True
                        queue.append((ny,nx))
        width, height = cx1-cx0+1, cy1-cy0+1
        if len(queue) >= 30 and width >= 3 and height >= 5 and width*100 <= 537*45 and height*100 <= 224*55:
            r['kept'] += 1; r['foreground_pixels'] += len(queue)
            x0, y0, x1, y1 = min(x0,cx0), min(y0,cy0), max(x1,cx1), max(y1,cy1)
    code = 0
    out = np.zeros((64,64), dtype=np.uint8)
    if not r['kept']:
        code = 3 if r['mean_gray'] < 24 else 1
    else:
        r.update(bbox_x=x0, bbox_y=y0, bbox_w=x1-x0+1, bbox_h=y1-y0+1)
        if r['mean_gray'] < 24: code = 3
        elif x0 < 4 or y0 < 4 or x1 >= 533 or y1 >= 220: code = 2
        else:
            margin = max(8, round_even(max(r['bbox_w'], r['bbox_h']), 10))
            cx, cy = max(0,x0-margin), max(0,y0-margin)
            ex, ey = min(537,x1+1+margin), min(224,y1+1+margin)
            r.update(crop_x=cx, crop_y=cy, crop_w=ex-cx, crop_h=ey-cy)
            crop = ink[cy:ey, cx:ex]
            nonzero = crop[crop != 0]
            high = quantile_milli(np.bincount(nonzero, minlength=256), nonzero.size, 995) if nonzero.size else 1000
            r['high_milli'] = max(1000, high)
            normalized = np.minimum(crop.astype(np.uint32)*180000//r['high_milli'], 255).astype(np.uint8)
            if r['high_milli'] < 12000: code = 4
            else: out = resize_canvas(normalized, r)
    r.update(code=code, code_name=CODES[code], input_crc=zlib.crc32(out.tobytes()))
    return out, r

