import os
import re
import glob

secret_patterns = [
    re.compile(r"BEGIN (?:RSA |OPENSSH |DSA |EC )?PRIVATE KEY"),
    re.compile(r"ghp_[A-Za-z0-9_]{36}"),
    re.compile(r"sk-[A-Za-z0-9]{48}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"password\s*[:=]\s*[\"'][^\"']{6,}[\"']", re.I),
]

files = glob.glob("evals/capri_comprehensive/reports/**", recursive=True) + glob.glob("evals/capri_comprehensive/artifacts/**", recursive=True)

leaks = []
for p in files:
    if os.path.isfile(p):
        try:
            with open(p, "r", errors="ignore") as f:
                content = f.read()
            for pat in secret_patterns:
                m = pat.findall(content)
                if m:
                    leaks.append((p, m[:3]))
        except Exception:
            pass

print(f"Scanned {len(files)} files.")
if leaks:
    print("Found potential secret leaks:")
    for path, matches in leaks:
        print(f"  {path}: {matches}")
else:
    print("ZERO host secrets or private credentials leaked in evals/capri_comprehensive/!")
