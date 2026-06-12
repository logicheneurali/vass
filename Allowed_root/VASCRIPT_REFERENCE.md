# VASScript Reference

## Overview
VASScript is a simple scripting language for VASS. Scripts are executed line by line. Lines starting with `#` are comments. Empty lines are skipped.

## Functions


### **`ai(prompt, memory?)`**
Sends a prompt to the AI and returns the response text. Optional `memory` parameter (boolean) — if true, includes permanent memory (summary + conversation history).

```
$result = ai("What is the capital of Italy?")
$result = ai("Dimmelo nella mia lingua", true)    # includes memory
say($result)
```


### **`say(text, speed?)`**
Reads text aloud via TTS (text-to-speech). Optional speed parameter (1.0 = normal, 1.5 = faster, 0.5 = slower). Requires authorization.

```
say("Hello world")
say("Hello world", 1.5)   # faster
say($variable, 0.8)       # slower

```


### **`run(command)`**
Executes a PowerShell command. Returns stdout and stderr as text. Requires authorization.

```
run("notepad.exe")
$processes = run("Get-Process | Select-Object -First 3")
say($processes)
```


### **`listen(prompt?)`**
Records voice input and returns the transcribed text. Optionally speaks a prompt first.

```
$name = listen("What is your name?")
say("Hello {$name}")
```


### **`wait(seconds)`**
Pauses execution for the specified number of seconds.

```
wait(2.5)
```


### **`exit()`**
Stops script execution immediately.


### **`screen_search(query)`**
Searches for text on screen using OCR. Returns JSON array of matches as a string.
Sets GLOBAL variables `$_sx`, `$_sy` (center x,y), `$_sw`, `$_sh` (width,height) for the first match.
These are regular VASScript variables — use them with `$` prefix like any other variable.

```
screen_search("Save")
screen_highlight($_sx, $_sy, $_sw, $_sh)
screen_click($_sx, $_sy)
```

```
screen_search("OK")
$found = ifempty($_sx, "Nothing found", "Found at {$_sx}, {$_sy}")
say($found)
```


### **`screen_click(x?, y?)`**
Clicks at specified coordinates. With no arguments, clicks at current position.

```
screen_click(500, 300)
screen_click($x, $y)
screen_click()
```


### **`screen_highlight(x, y, w?, h?, dur?)`**
Highlights an area on screen (red rectangle). Default size: 100x50. Default duration: 1.0s.

```
screen_highlight(500, 300, 200, 100, 2.0)
```


### **`setActiveWindow(name)`**
Activates a window by process name or title substring (case-insensitive, requires authorization).
First searches by process name, then by window title.
Returns "ok" if found, "not found" otherwise.

```
setActiveWindow("firefox")
setActiveWindow("notepad")
$result = setActiveWindow("chrome")
say("Window: {$result}")
```


### **`sendText(text)`**
Simulates typing each character with human-like random delays (0.10-0.15s between keys).
Supports `\n` for Enter key and `\t` for Tab key. Requires authorization.

```
sendText("Hello World")
sendText("First line\nSecond line")
setActiveWindow("notepad")
wait(0.5)
sendText("VASS says hello!")
```


### **`addevent(date, time, duration, description, recur?)`**
Adds an event to events.json. Requires authorization. Name is auto-generated.
Optional `recur` parameter for recurring events: "1d"=daily, "7d"=weekly, "1m"=monthly, "2h"=every 2 hours.

```
addevent("2026-06-10", "14:30", "60", "Riunione team")
addevent("2026-06-12", "08:00", "5", "Pillola", "1d")    # every day
addevent("2026-06-02", "09:00", "30", "Chiamata", "7d")  # weekly

```


### **`listevents(until_date)`**
Lists upcoming events from today to until_date. Returns a JSON array.

```
$events = listevents("2026-12-31")
say($events)
```


### **`removeevent(description, date?, time?)`**
Removes an event by fuzzy-matching the description (threshold 0.75). Requires authorization.
Optional `date` (`YYYY-MM-DD`) and `time` (`HH:MM`) to disambiguate matching events.
If multiple events match without date/time, returns the list instead of deleting.
Alias: `delevent(description, date?, time?)`
```
removeevent("riunione team")
delevent("Meeting", "2026-06-15", "14:00")
$result = removeevent("chiamata")
say($result)                    # says "ok: removed 'Chiamata' on 2026-06-12 at 09:00"
```


### **`savetags(tags)`**
Classifies the current message with comma-separated memory tags. Tags are validated against a predefined list. Only saved if total relevance >= 10. No auth required.

```
savetags("food,health,pets")    # saves to memory_tags.json if relevance >= 10
$result = savetags("generic")   # returns "skipped: relevance 1 < 10"
```


### **`timer_start(duration)`**
Starts a countdown timer. Duration in compact format (e.g. `1h`, `20m`, `30s`, `1h30m`). Max 5 simultaneous timers. Minimum 1 minute. No auth required.

```
$r = timer_start("1h30m")
say($r)    # says "Timer: avviato"
```


### **`timer_list()`**
Lists active timers with remaining time. No auth required.

```
$list = timer_list()
say($list)    # says "Timer attivi:\n  abc123: 1h30m (54m remaining)"
```


### **`timer_cancel(id)`**
Cancels a timer by its ID. No auth required.

```
$r = timer_cancel("abc123")
say($r)    # says "Timer abc123 cancellato"
```


### **`notify(text, priority?)`**
Creates an in-app notification with optional priority (1-10, default 1). Appears in the bell icon popup. No auth required.

```
notify("Timer scaduto", 8)
notify("Operazione completata")
```


### **`getdatetime()`**
Returns current local date and time in "YYYY-MM-DD HH:MM" format. No auth required.

```
$now = getdatetime()
say($now)    # says "2026-06-02 14:30"
```


### **`prettyevents(json)`**
Formats the JSON output of listevents() into readable text. No auth required.

```
$events = listevents("2026-12-31")
$text = prettyevents($events)
say($text)    # says "Monday 02 June 2026 14:30 Riunione (60 min)"
```


### **`clipboardget()`**
Returns the current clipboard text content. Requires authorization.

```
$text = clipboardget()
say($text)
```


### **`clipboardset(text)`**
Sets the clipboard text content. Requires authorization.

```
clipboardset("Hello from VASS")
```


### **`readinfo(id)`**
Reads an info file by its ID from the memory storage. Requires authorization.

```
$info = readinfo("1780297134565")
say($info)
```


### **`writeinfo(text)`**
Writes text to a new info file. Returns the file ID. Requires authorization.

```
$id = writeinfo("Important user data")
say("Saved with ID: {$id}")
```

## Conditional Functions


### **`ifcontains(variable, substring, if_true, if_false?)`**
Checks if variable contains substring. Returns value from the appropriate branch.

```
$status = ifcontains($response, "error", "Failed", "Success")
say($status)
```


### **`ifempty(variable, if_empty, if_not_empty?)`**
Checks if variable is empty.

```
$name = ifempty($username, "Guest", $username)
say("Welcome {$name}")
```

## Utility Functions


### **`trim(text)`**
Removes leading and trailing whitespace.


### **`len(text)`**
Returns the length of a text string.


### **`contains(text, substring)`**
Returns "True" or "False" depending on whether text contains substring.


### **`equals(a, b)`**
Returns "True" or "False" depending on whether a equals b.

## Built-in Variables

These variables are automatically available in every VASScript script.


### **`$_lang`**
Contains the current language code (e.g. `"it"`, `"en"`, `"de"`, `"fr"`, `"es"`, `"pt"`, `"ja"`, `"ko"`, `"zh"`).

```
say("Current language is {$_lang}")
$dt = getdatetime($_lang)   # formatted in current language

```


### **`$_exec_message`**
Contains the localized execution script message (e.g. "Script execution"). Useful for UI feedback.

```
say($_exec_message)
```

## Variables

Variables start with `$` and are assigned with `=`.

```
$name = "Fabio"
$age = "54"
$result = ai("Hello")

$combined = "{$name} is {$age}"
say($combined)
```

Variable interpolation in strings: `{variable}`.

```
$name = "World"
say("Hello {name}")
say("Hello {$name}")
```

## Examples


### News summarizer

```
$news = ai("Find the latest 3 news headlines and summarize each in one sentence")
say($news)
```


### Interactive script

```
$name = listen("What is your name?")
say("Hello {$name}")
$color = listen("What is your favorite color?")
$response = ai("Tell me an interesting fact about the color {$color}")
say($response)
```


### Screen automation

```
screen_highlight(100, 100, 200, 50)
$found = screen_search("Login")
ifcontains($found, "Login", say("Login button found"), say("Not found"))
```
