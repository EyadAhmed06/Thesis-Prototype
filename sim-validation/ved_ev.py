import py7zr, pandas as pd, glob, os, sys
D=sys.argv[1]; X=sys.argv[2]; os.makedirs(X,exist_ok=True)
for f in sorted(glob.glob(D+'/*.7z')):
    with py7zr.SevenZipFile(f) as z: z.extractall(X)
ev={10,455,541}; parts=[]
for c in sorted(glob.glob(X+'/**/*.csv',recursive=True)):
    for ch in pd.read_csv(c,chunksize=500000,low_memory=False):
        parts.append(ch[ch.VehId.isin(ev)])
    os.remove(c)
d=pd.concat(parts); d.to_parquet(sys.argv[3]) if False else d.to_csv(sys.argv[3],index=False)
print(len(d),'rows',d.groupby('VehId').Trip.nunique().to_dict())
