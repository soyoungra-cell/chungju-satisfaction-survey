# 잔잔한 피아노 + 패드 배경음악 (직접 합성, 저작권 걱정 없음)
import numpy as np, wave
SR=44100; BPM=72; BEAT=60/BPM; BAR=4*BEAT
TOTAL=63.0
N=int(SR*TOTAL); L=np.zeros(N); Rr=np.zeros(N)
rng=np.random.default_rng(7)
def hz(m): return 440*2**((m-69)/12)
def piano(m,t0,vel=0.5,dur=4.0,pan=0.0):
    f=hz(m); n=int(dur*SR); t=np.arange(n)/SR
    s=np.zeros(n)
    for k in range(1,7):
        if f*k>12000: break
        s+=np.sin(2*np.pi*f*k*t*(1+0.0004*k))*(1/k**1.6)*np.exp(-t*(0.9+0.9*k)*(f/440)**0.35)
    s*=np.minimum(1,t/0.005)
    s*=np.minimum(1,(dur-t)/0.3).clip(0)
    add(s*vel,t0,pan)
def pad(ms,t0,dur,vel=0.08):
    n=int(dur*SR); t=np.arange(n)/SR
    s=np.zeros(n)
    for m in ms:
        f=hz(m)
        for d in (-0.12,0.12):
            ff=f*2**(d/12/10)
            s+=np.sin(2*np.pi*ff*t)+0.25*np.sin(2*np.pi*2*ff*t)
    env=np.minimum(1,t/1.2)*np.minimum(1,(dur-t)/1.4).clip(0)
    add(s*env*vel/len(ms),t0,0)
def add(s,t0,pan):
    i=int(t0*SR); j=min(N,i+len(s)); s=s[:j-i]
    L[i:j]+=s*np.sqrt((1-pan)/2); Rr[i:j]+=s*np.sqrt((1+pan)/2)
# 화음 (MIDI) : 저음, 화음 구성음
C=[48,[60,64,67,71,74]]; GB=[47,[59,62,67,71,74]]; Am=[45,[57,60,64,67,71]]; F=[41,[57,60,64,65,69]]
Dm=[50,[57,60,62,65,69]]; Em=[52,[59,62,64,67,71]]; Gs=[43,[59,62,65,67,72]]
prog=[C,GB,Am,F,Dm,Em,F,Gs]
nbars=int(TOTAL/BAR)
arp=[0,2,1,3,2,4,3,1]
for b in range(nbars):
    t0=b*BAR
    last = b>=17
    ch = C if last else prog[b%8]
    if b==16: ch=F
    bass,tones=ch
    pad([bass+12]+tones[:3],t0,BAR+1.5,0.07 if b>1 else 0.05)
    if last:
        if b==17:
            piano(bass,t0,0.45,7); piano(bass+12,t0+0.02,0.3,7)
            for i,m in enumerate([64,67,72,74,79]): piano(m,t0+0.35*i+0.1,0.22,7,pan=-0.3+0.15*i)
        continue
    piano(bass,t0,0.42 if b>2 else 0.3,BAR+0.8,pan=-0.2)
    if b<3:   # 도입: 여백 있게
        for i,m in enumerate(tones[1::2]): piano(m+12,t0+BEAT*(1+i*1.5),0.16,3,pan=0.2)
        continue
    for i in range(8):
        m=tones[arp[i]]+12
        v=0.13+0.05*(i%4==0)+rng.uniform(-0.015,0.015)
        piano(m,t0+i*BEAT/2+rng.uniform(0,0.012),v,2.6,pan=0.25*np.sin(i))
    if b%2==1:  # 멜로디 한 음
        piano(tones[4]+12,t0+BEAT*2.5,0.2,3.2,pan=0.1)
# 리버브 (합성 임펄스 응답)
def reverb(x,seed):
    r=np.random.default_rng(seed); n=int(2.2*SR); t=np.arange(n)/SR
    ir=r.standard_normal(n)*np.exp(-t*2.6); ir[:int(.012*SR)]=0
    ir/=np.sqrt((ir**2).sum())
    m=len(x)+n; F=1<<int(np.ceil(np.log2(m)))
    y=np.fft.irfft(np.fft.rfft(x,F)*np.fft.rfft(ir,F),F)[:len(x)]
    return y
# 부드럽게: 간단한 저역통과
def lp(x,a=0.35):
    y=np.empty_like(x); z=0.0
    b=np.array(x)
    from itertools import accumulate
    return np.convolve(x,np.ones(3)/3,'same')
wl=lp(L)+0.45*reverb(L,1); wr=lp(Rr)+0.45*reverb(Rr,2)
st=np.stack([wl,wr],1)
t=np.arange(N)/SR
st*=np.minimum(1,t/1.5)[:,None]
st*=np.clip((TOTAL-t)/3.0,0,1)[:,None]**1.5
st/=np.abs(st).max()/0.7
with wave.open('bgm.wav','wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st*32767).astype('<i2').tobytes())
print('ok',TOTAL)
