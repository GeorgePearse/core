# Basic Setup for `ALE-Bench`

```
conda create -n ale_bench python=3.11
conda active ale_bench
git clone https://github.com/SakanaAI/ALE-Bench.git

cd ALE-Bench
pip install .

# This seems to take a while!
bash ./scripts/docker_build_all.sh $(id -u) $(id -g)
```

Execute one program evaluation

```
python evaluate.py --program_path initial.cpp
```