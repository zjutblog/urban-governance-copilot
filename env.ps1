# env.ps1 —— 在当前 PowerShell 会话中激活 urban_agent 环境
# 用法（在项目根目录执行）：
#   . .\env.ps1
# 之后 python / pip 都会指向 urban_agent 环境
& "D:\anacanda\shell\condabin\conda-hook.ps1"
conda activate urban_agent
python --version
