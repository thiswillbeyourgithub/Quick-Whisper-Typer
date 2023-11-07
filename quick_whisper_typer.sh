#!/usr/bin/zsh

# set -euxo pipefail

# Parsing command line arguments as an array
LANG=""
PROMPT=""
TRANSFORM=0
for arg in "$@"; do
    case "$arg" in
        -l | --language)
            LANG="$2"
            shift 2
            ;;
        -p | --prompt)
            PROMPT="$2"
            shift 2
            ;;
        -t | --transform_clipboard)
            TRANSFORM=1
            shift 2
            ;;
        #*)
        #    echo "Invalid option: $arg"
        #    exit 1
        #    ;;
    esac
done
echo "Will use language $LANG and prompt $PROMPT and transform $TRANSFORM "

# check if the language is supplied and correct
allowed_langs=("fr" "en")
if [[ -z "$LANG" || ! " ${allowed_langs[@]}  " =~ " $LANG " ]]
then
    echo "Invalid lang $LANG"
    exit 1
fi

if [[ -z "$PROMPT" ]]
then
    if [[ "$LANG" == "fr" ]]
    then
        PROMPT="Dictée vocale sur mon téléphone: "
     elif [[ "$LANG" == "en" ]]
    then
        PROMPT="Dictation on my smartphone: "
    fi
fi


# load openai api key
cd "$(dirname "$0")"
export OPENAI_API_KEY=$(cat ./API_KEY.txt)

FILE="/tmp/audio_recording_$(date +%s).mp3"
start_time=$(date +%s)
min_duration=3  # if the recording is shorter, exit

record() {
    log "Recording $1"
    rec -r 44000 -c 1 -b 16 "$1" &
}

log() {
    echo $1
    echo "$(date +%s) $1" >> ./texts.log
}


# kill just in case was already running
killall rec >/dev/null 2>&1

# start recording
record $FILE

# give time to the user to position the cursor
sleep 1

# yad form
instruction=$(yad \
    --form \
    --title "Yad Sound Recorder" \
    --field "ChatGPT instruction" \
    --on-top \
    --button="STOP!gtk-media-stop":0
    )
log "\nChatGPT instruction: $instruction for task $TRANSFORM"

# kill the recording
killall rec >/dev/null 2>&1
log "Done recording $FILE"

# check duration
end_time=$(date +%s)
duration=$((end_time - start_time))
log "Duration $duration"
if (( duration < min_duration ))
then
    log "Recording too short ($duration s), exiting without calling whisper."
    sleep 1
    log ""
    exit 0
fi


# echo "playing file"
# mplayer $FILE

# removing silences longer than Xs
rm /tmp/tmpoutput*.mp3
sox $FILE /tmp/tmpoutput.mp3 silence 1 1 0.1% 1 1 0.1% : newfile : restart
cat /tmp/tmpoutput*.mp3 > "/tmp/unsilenced_$FILE"
rm /tmp/tmpout*.mp3
$FILE="unsilenced_$FILE"
log "Removed silence, new file is $FILE"

log "Calling whisper"
text=$(openai api audio.transcribe --model whisper-1 --response-format text --temperature 0 -f $FILE  --language $LANG --prompt "$PROMPT")
log "Whisper transcript: $text"

prev_clipboard=$(xclip -o -sel clipboard)

if [[ $TRANSFORM == "1" ]]
    then
    log "Calling ChatGPT with instruction $instruction to transform the clipboard"
    log "current keyboard: $prev_clipboard"
    text=$(openai api chat_completions.create --model gpt-3.5-turbo-1106 -g system "You transform INPUT_TEXT according to an instruction. Only reply the transformed text without anything else." -g user "INPUT_TEXT: '$prev_clipboard'\n\nINSTRUCTION: '$text'")
    log "ChatGPT answer after transformation: $text"
    fi

if [[ ! -z $instruction ]]
then
    log "Calling ChatGPT with instruction $instruction"
    text=$(openai api chat_completions.create --model gpt-3.5-turbo-1106 -g system "You transform INPUT_TEXT according to an instruction. Only reply the transformed text without anything else." -g user "INPUT_TEXT: '$text'\n\nINSTRUCTION: '$instruction'")
    log "ChatGPT output: $text"
else
    log "Not using ChatGPT"
fi


# save to all clipboard just in case
echo "$text" | xclip -sel primary
echo "$text" | xclip -sel secondary
echo "$text" | xclip -sel clipoard
xdotool key ctrl+v
echo "$prev_clipboard" | xclip -sel clipboard
