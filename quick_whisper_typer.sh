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
    echo "Recording $1"
    rec -r 44000 -c 1 -b 16 "$1" &
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
echo "\nChatGPT instruction: $instruction for task $TRANSFORM"

# kill the recording
killall rec >/dev/null 2>&1
echo "Done recording $FILE"

# check duration
end_time=$(date +%s)
duration=$((end_time - start_time))
echo "Duration $duration"
if (( duration < min_duration ))
then
    echo "Recording too short ($duration s), exiting without calling whisper."
    sleep 1
    echo ""
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
echo "Removed silence, new file is $FILE"

echo "Calling whisper"
text=$(openai api audio.transcribe --model whisper-1 --response-format text --temperature 0 -f $FILE  --language $LANG --prompt "$PROMPT")
echo "Whisper transcript: $text"

prev_clipboard=$(xclip -o -sel clip)

if [[ $TRANSFORM == "1" ]]
    then
    echo "Calling ChatGPT with instruction $input to transform the clipboard"
    echo "current keyboard: $prev_clipboard"
    text=$(openai api chat_completions.create --model gpt-3.5-turbo -g system "You transform INPUT_TEXT according to an instruction. Only reply the transformed text without anything else." -g user "INPUT_TEXT:'$prev_clipboard'\n\nINSTRUCTION: '$text'")
    echo "ChatGPT answer after transformation: $text"
    fi

if [[ ! -z $instruction ]]
then
    echo "Calling ChatGPT with instruction $instruction"
    text=$(openai api chat_completions.create --model gpt-3.5-turbo -g system "$input" -g user "$text")
    echo "ChatGPT output: $text"
else
    echo "Not using ChatGPT"
fi


echo "$text" | xclip -sel clip
xdotool key ctrl+v
echo "$prev_clipboard" | xclip -sel clip
