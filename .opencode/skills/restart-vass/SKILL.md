---
name: restart-vass
description: Kill all VASS processes (including subprocesses like MCP server, llama.cpp) and restart the application. Use ONLY when the user asks to restart/riavviare the VASS app.
---

# Restart VASS

Kills all running VASS-related Python processes and their subtrees, then starts `vass.py`.

## Commands

### Kill all VASS processes

```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
    Where-Object { $_.CommandLine -match 'vass' } |
    ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>$null }
Start-Sleep 2
```

This kills every Python process whose command line contains `vass`, including:
- The main `vass.py` process
- MCP server subprocess
- llama.cpp subprocess
- Any open editors (settings_editor.py, commands_editor.py)

### Start the application

```powershell
Start-Process -FilePath "python" -ArgumentList "C:\Users\effed\Documents\Python\vass\vass.py" -WindowStyle Normal
```

### One-liner (kill + start)

```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" |
    Where-Object { $_.CommandLine -match 'vass' } |
    ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>$null }; `
Start-Sleep 2; `
Start-Process -FilePath "python" -ArgumentList "C:\Users\effed\Documents\Python\vass\vass.py" -WindowStyle Normal
```
