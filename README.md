# Quick Whisper Typer
Super simple zsh script to start recording sound, send it to whisper then have it type for you in a field.

## Features
* Automatically stops if you move the mouse too much. You are supposed to launch the script, move the mouse to the field you want to type int, then press Escape to exit the yad window. This will then trigger the whisper code.
* Input argmuent allows to choose the language
* One can quickly use openai chatgpt to correct texts like that, including on the go translation etc
* Removes long silences via sox

## How to
* Put your OpenAI api key in a file called API_KEY.txt
* *optional: add a keyboard shortcut to call this script. See my i3 bindings below.*
* launch the script
* the recording starts instantly
* move quickly your mouse to select the field you want to type in
* after 1s a minimalist yad window appears and takes focus away from the field
* press Escape to exit the yad window, this will trigger whisper
* when whisper is done, xdotool will type for you (every few keystrokes, the script will check that your mouse has not moved to avoid launching random shortcuts into other apps)
* If you enter a text in the field, it will be passed as instruction to chatgpt to transform the whisper output

### i3 bindings
```
mode "$mode_launch_microphone" {
    bindsym f exec /PATH/TO/Yad_Quick_Microphone.sh fr, mode "default
    bindsym e exec /PATH/TO/Yad_Quick_Microphone.sh en, mode "default"

    bindsym Return mode "default"
    bindsym Escape mode "default"
    bindsym $alt+shift+r mode "default"
    }

```
