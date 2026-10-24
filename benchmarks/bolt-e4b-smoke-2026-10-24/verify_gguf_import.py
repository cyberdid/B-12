from pathlib import Path
import struct,hashlib,json
root=Path('/home/cyberdid/Projects/B-12/benchmarks/bolt-e4b-smoke-2026-10-24')
source=Path('/home/cyberdid/Downloads/B-12-models/bolt-e4b-q4/Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf')
imported=Path('/usr/share/ollama/.ollama/models/blobs/sha256-49eca097c81e38013c4a6278ade7d8541f4a50918000ee16f73ee151ca01c8bc')
def parse(path):
 with path.open('rb') as f:
  def u32():return struct.unpack('<I',f.read(4))[0]
  def u64():return struct.unpack('<Q',f.read(8))[0]
  def string():return f.read(u64()).decode('utf-8')
  def skip(kind):
   sizes={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
   if kind in sizes:f.seek(sizes[kind],1)
   elif kind==8:f.seek(u64(),1)
   elif kind==9:
    sub=u32();n=u64()
    if sub in sizes:f.seek(sizes[sub]*n,1)
    else:
     for _ in range(n):skip(sub)
   else:raise RuntimeError(f'Unsupported metadata kind {kind}')
  assert f.read(4)==b'GGUF';version=u32();nt=u64();nk=u64();metadata={};alignment=32
  for _ in range(nk):
   key=string();kind=u32();start=f.tell();skip(kind);end=f.tell();f.seek(start);raw=f.read(end-start)
   metadata[key]=hashlib.sha256(raw).hexdigest()
   if key=='general.alignment':alignment=int.from_bytes(raw,'little')
  tensors=[]
  for _ in range(nt):
   name=string();dims=u32();shape=[u64() for _ in range(dims)];kind=u32();offset=u64()
   tensors.append({'name':name,'shape':shape,'type':kind,'offset':offset})
  data_offset=(f.tell()+alignment-1)//alignment*alignment;f.seek(data_offset)
  digest=hashlib.sha256()
  while block:=f.read(8*1024*1024):digest.update(block)
  return {'version':version,'tensor_count':nt,'metadata_keys':nk,'metadata_hashes':metadata,'tensors':tensors,'data_offset':data_offset,'tensor_payload_sha256':digest.hexdigest()}
a=parse(source);b=parse(imported)
keys=set(a['metadata_hashes'])|set(b['metadata_hashes'])
report={'source_gguf':str(source),'imported_gguf':str(imported),'source_sha256':'c8af2b8aea10a690a1d9491db744a9446660173cb38fc489612b556615a69612','imported_blob_digest':'49eca097c81e38013c4a6278ade7d8541f4a50918000ee16f73ee151ca01c8bc','source_tensor_count':a['tensor_count'],'imported_tensor_count':b['tensor_count'],'source_data_offset':a['data_offset'],'imported_data_offset':b['data_offset'],'changed_metadata_keys':sorted(k for k in keys if a['metadata_hashes'].get(k)!=b['metadata_hashes'].get(k)),'tensor_table_equal':a['tensors']==b['tensors'],'tensor_payload_equal':a['tensor_payload_sha256']==b['tensor_payload_sha256'],'source_tensor_payload_sha256':a['tensor_payload_sha256'],'imported_tensor_payload_sha256':b['tensor_payload_sha256']}
with imported.open('rb') as stream:
 report['imported_file_sha256_actual']=hashlib.file_digest(stream,'sha256').hexdigest()
with source.open('rb') as left_stream, imported.open('rb') as right_stream:
 left=left_stream.read(a['data_offset']);right=right_stream.read(b['data_offset'])
 report['header_bytes_equal']=left==right
 report['header_differing_bytes']=sum(x!=y for x,y in zip(left,right))
(root/'gguf-import-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False),flush=True)
if not report['tensor_table_equal'] or not report['tensor_payload_equal']:raise SystemExit(1)
