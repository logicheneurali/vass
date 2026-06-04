param([int]$x=200, [int]$y=200, [int]$w=300, [int]$h=100, [double]$dur=5)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.FormBorderStyle = 'None'
$form.BackColor = 'Fuchsia'
$form.TransparencyKey = 'Fuchsia'
$form.TopMost = $true
$form.ShowInTaskbar = $false
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point -ArgumentList $x, $y
$form.Size = New-Object System.Drawing.Size -ArgumentList $w, $h

$inner = New-Object System.Windows.Forms.Panel
$inner.BackColor = 'DeepSkyBlue'
$inner.Location = New-Object System.Drawing.Point -ArgumentList 3, 3
$inner.Size = New-Object System.Drawing.Size -ArgumentList ($w - 6), ($h - 6)
$inner.BorderStyle = 'FixedSingle'
$form.Controls.Add($inner)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = [int]($dur * 1000.0)
$timer.Add_Tick({ $timer.Stop(); $form.Close() })
$timer.Start()

$form.ShowDialog()
