# Спутниковая карта Эгейского моря (Афины — Санторини) по координатам: lon 22.91–26.19, lat 35.26–39.14.
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi
rng = np.random.default_rng(7)
W, H = 1000, 1480
LON0, LON1, LAT0, LAT1 = 22.91, 26.19, 35.26, 39.14
px = lambda lon, lat: ((lon-LON0)/(LON1-LON0)*W, (LAT1-lat)/(LAT1-LAT0)*H)

def fbm(shape, octaves, base, persist=.55, seed=0):
    r = np.random.default_rng(seed); out = np.zeros(shape, np.float32); amp = 1; tot = 0
    for o in range(octaves):
        s = base * (2 ** o)
        n = r.standard_normal((max(2, shape[0]//s+2), max(2, shape[1]//s+2))).astype(np.float32)
        n = ndi.zoom(n, (shape[0]/n.shape[0], shape[1]/n.shape[1]), order=3)[:shape[0], :shape[1]]
        out += n*amp; tot += amp; amp *= persist
    out /= tot; return (out-out.min())/(out.max()-out.min())

land_img = Image.new("L", (W, H), 0); d = ImageDraw.Draw(land_img)
def poly(pts): d.polygon([px(*p) for p in pts], fill=255)
def blob(lon, lat, rx, ry, rot=0, n=26):  # остров: неправильный эллипс
    t = np.linspace(0, 2*np.pi, n, endpoint=False); k = 1 + .22*rng.standard_normal(n)
    x = rx*np.cos(t)*k; y = ry*np.sin(t)*k; c, s = np.cos(np.radians(rot)), np.sin(np.radians(rot))
    poly([(lon+x[i]*c-y[i]*s, lat+x[i]*s+y[i]*c) for i in range(n)])
# материк + Пелопоннес (восточная часть)
poly([(22.0,39.9),(22.9,39.5),(23.30,39.30),(23.10,39.00),(23.32,38.72),(23.60,38.50),(23.95,38.30),(24.00,38.05),(24.12,37.80),(24.05,37.66),(23.88,37.72),(23.74,37.83),(23.60,37.92),(23.50,38.03),(23.20,37.95),(23.00,37.93),(23.15,37.70),(23.38,37.62),(23.32,37.44),(23.12,37.34),(22.95,37.20),(22.80,37.12),(22.92,36.90),(23.04,36.68),(23.20,36.44),(23.00,36.38),(22.0,36.38)])
# Эвия
poly([(23.20,39.12),(23.45,38.97),(23.68,38.66),(23.98,38.40),(24.22,38.20),(24.46,38.06),(24.62,37.98),(24.42,38.12),(24.12,38.32),(23.88,38.52),(23.62,38.52),(23.40,38.80),(23.08,38.98)])
# Крит (северный берег)
poly([(23.40,34.6),(23.52,35.48),(24.02,35.56),(24.45,35.46),(24.90,35.40),(25.30,35.36),(25.72,35.36),(26.05,35.30),(26.30,35.10),(26.30,34.6)])
for b in [(23.50,37.95,.09,.07,0),(23.48,37.72,.07,.05,20),(23.45,37.50,.05,.04,0),(23.45,37.33,.04,.13,-50),(23.15,37.25,.04,.03,0),(24.33,37.62,.07,.16,-15),(24.43,37.40,.05,.14,-20),
          (24.50,37.15,.07,.06,0),(24.72,36.98,.05,.12,15),(24.42,36.72,.10,.08,0),(24.80,37.83,.11,.28,-35),(25.15,37.57,.06,.17,-20),(24.93,37.44,.06,.06,0),(25.40,37.45,.09,.07,0),
          (25.18,37.05,.10,.11,0),(25.50,37.05,.16,.21,10),(25.35,36.72,.07,.12,-10),(25.90,36.83,.05,.26,-60),(24.92,36.63,.09,.05,0),(25.12,36.65,.04,.04,0),(25.77,36.35,.06,.05,0),
          (24.55,38.88,.08,.28,-55),(23.50,39.15,.12,.07,0),(26.02,38.35,.13,.26,-10),(26.15,37.62,.07,.30,-70),(25.58,36.95,.04,.06,0),(24.72,36.72,.04,.04,0)]: blob(*b)
# Санторини — полумесяц вокруг кальдеры
t = np.linspace(.35, 2*np.pi-.55, 40); poly([(25.43+.12*np.cos(a)*(1+.05*rng.standard_normal()), 36.41+.12*np.sin(a)*(1+.05*rng.standard_normal())) for a in t] + [(25.43+.065*np.cos(a), 36.41+.065*np.sin(a)) for a in t[::-1]])
blob(25.37,36.40,.025,.035,0)  # Тирасия
land = np.array(land_img).astype(np.float32)/255
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
# неровный берег: крупное + мелкое смещение границы
dx = (fbm((H, W), 3, 60, seed=3)-.5)*26 + (fbm((H, W), 5, 7, .6, seed=4)-.5)*14
dy = (fbm((H, W), 3, 60, seed=5)-.5)*26 + (fbm((H, W), 5, 7, .6, seed=6)-.5)*14
land = ndi.map_coordinates(ndi.gaussian_filter(land, 2.0), [yy+dy, xx+dx], order=1)
mask = ndi.gaussian_filter(land, .8) > .5
dist_in = ndi.distance_transform_edt(mask); dist_out = ndi.distance_transform_edt(~mask)
# --- суша: рельеф с мелкой детализацией ---
big = fbm((H, W), 4, 120, .55, seed=11); mid_ = fbm((H, W), 6, 28, .6, seed=12); fine = fbm((H, W), 6, 6, .62, seed=13)
ridge = 1 - np.abs(2*fbm((H, W), 6, 48, .58, seed=21) - 1)
inland = np.clip(.25 + dist_in/55, 0, 1)
elev = np.clip((big*.35 + mid_*.3 + fine*.12 + ridge*.5)*inland, 0, 1)
elev = (elev-elev[mask].min())/(elev[mask].max()-elev[mask].min())
gy, gx = np.gradient(ndi.gaussian_filter(elev, .9)); shade = np.clip(.5 + 11*(-gx*.7 + gy*.7), 0, 1)
green = np.array([118, 150, 72]); olive = np.array([104, 122, 62]); brown = np.array([150, 116, 78]); rock = np.array([196, 180, 150])
e = elev[..., None]
col = np.where(e < .4, green + (olive-green)*(e/.4), np.where(e < .68, olive + (brown-olive)*((e-.4)/.28), brown + (rock-brown)*np.clip((e-.68)/.32, 0, 1)))
dry = (fbm((H, W), 5, 50, seed=31)-.35).clip(0, 1)[..., None]*1.5; col = col*(1-.35*dry) + np.array([184, 164, 100])*.35*dry
veg = (fbm((H, W), 6, 16, seed=41)-.45).clip(0, 1)[..., None]*1.8; col = col*(1-.35*veg) + np.array([52, 98, 48])*.35*veg
col = col*(.55 + .85*shade[..., None])*(.94 + .12*fine[..., None])
# --- море ---
depth = np.clip(dist_out/230, 0, 1)**.62
depth = np.clip(depth + (fbm((H, W), 4, 140, seed=51)-.5)*.3, 0, 1)[..., None]
shallow = np.array([70, 205, 214]); mids = np.array([22, 132, 208]); deep = np.array([8, 72, 164])
sea = np.where(depth < .38, shallow + (mids-shallow)*(depth/.38), mids + (deep-mids)*np.clip((depth-.38)/.62, 0, 1))
sea = sea + ((fbm((H, W), 5, 10, seed=61)-.5)[..., None]*22) + ((fbm((H, W), 3, 90, seed=62)-.5)[..., None]*16)
img = np.where(mask[..., None], col, sea)
edge = np.exp(-dist_out/2.0)*(~mask)*.9
img = img*(1-.4*edge[..., None]) + np.array([232, 246, 248])*.4*edge[..., None]
# --- облака: только по правому краю (как на референсе), не закрывают города и маршрут ---
cl = fbm((H, W), 6, 90, .6, seed=71)
cx = np.linspace(0, 1, W)[None, :]; cy = np.linspace(0, 1, H)[:, None]
g = lambda c, w, y0, h: np.exp(-((cx-c)/w)**2)*np.exp(-((cy-y0)/h)**2)
bias = .5*g(1.02, .2, .10, .09) + .5*g(1.02, .2, .46, .1) + .55*g(1.0, .22, .94, .06) + .3*g(.0, .12, .03, .05)
bn = np.clip(bias/.55, 0, 1)                          # облака только там, где есть «зона облаков»
cld = np.clip((cl*bn*1.5 + bn*.25 - .42)/.18, 0, 1); cld = ndi.gaussian_filter(cld, 3)
sh = ndi.shift(ndi.gaussian_filter(cld, 7), (14, -9), order=1)
img = img*(1-.22*sh[..., None]); img = img*(1-cld[..., None]*.93) + np.array([251, 253, 255])*cld[..., None]*.93
out = np.clip(img, 0, 255).astype(np.uint8)
Image.fromarray(out).filter(ImageFilter.UnsharpMask(1.6, 90, 2)).save("greece-map.jpg", quality=84, optimize=True, progressive=True)
print("ok")
