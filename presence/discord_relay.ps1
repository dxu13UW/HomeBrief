# Relay between focus_presence.py (in WSL) and the Discord desktop client's local IPC pipe.
# Discord's pipe is a Windows named pipe, which WSL can't open, so this script does only that:
# each stdin line is {"op": <int>, "data": {...}}; it is framed (op and length as little-endian
# int32, then UTF-8 JSON) and written to the pipe. Each reply frame is printed as one JSON line.
# The first line printed is this process's PID, which Discord ties the presence to.

$ErrorActionPreference = "Stop"
[Console]::Out.WriteLine((@{ pid = $PID } | ConvertTo-Json -Compress))

$pipe = $null
foreach ($i in 0..9) {
    $candidate = New-Object System.IO.Pipes.NamedPipeClientStream(".", "discord-ipc-$i", [System.IO.Pipes.PipeDirection]::InOut)
    try { $candidate.Connect(500); $pipe = $candidate; break } catch { $candidate.Dispose() }
}
if (-not $pipe) {
    [Console]::Out.WriteLine('{"error":"Discord is not running"}')
    exit 1
}

function Read-Exactly([int]$count) {
    $buffer = New-Object byte[] $count
    $read = 0
    while ($read -lt $count) {
        $n = $pipe.Read($buffer, $read, $count - $read)
        if ($n -le 0) { throw "Discord closed the connection" }
        $read += $n
    }
    return ,$buffer
}

$stdin = [Console]::In
while ($null -ne ($line = $stdin.ReadLine())) {
    $message = $line | ConvertFrom-Json
    $body = [System.Text.Encoding]::UTF8.GetBytes(($message.data | ConvertTo-Json -Compress -Depth 10))
    $frame = [BitConverter]::GetBytes([int]$message.op) + [BitConverter]::GetBytes([int]$body.Length) + $body
    $pipe.Write($frame, 0, $frame.Length)
    $pipe.Flush()

    $header = Read-Exactly 8
    $length = [BitConverter]::ToInt32($header, 4)
    $reply = [System.Text.Encoding]::UTF8.GetString((Read-Exactly $length))
    [Console]::Out.WriteLine($reply)
}
$pipe.Dispose()
