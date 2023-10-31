#!/usr/bin/zsh

# set -euxo pipefail

# check if the language is supplied
LANG=$1
allowed_langs=("fr" "en")
if [[ -z "$LANG" || ! " ${allowed_langs[@]}  " =~ " $LANG " ]]
then
    echo "Invalid lang $LANG"
    exit 1
fi

if [[ "$LANG" == "fr" ]]
then
    PROMPT="Dictée vocale sur mon téléphone: "
 elif [[ "$LANG" == "en" ]]
then
    PROMPT="Dictation on my smartphone: "
fi


# load openai api key
cd "$(dirname "$0")"
export OPENAI_API_KEY=$(cat ./API_KEY.txt)

# if using azerty, make sure to use french keyboard for xdotool
setxkbmap fr

FILE="/tmp/audio_recording_$(date +%s).mp3"
start_time=$(date +%s)
min_duration=3  # if the recording is shorter, exit
max_distance=2  # mouse distance above which we stop typing

record() {
    echo "Recording $1"
    rec -r 44000 -c 1 -b 16 "$1" &
}
type_input() {
    # xdotool type --delay 0 "$1" 2>/dev/null
    xdotool key --delay 0 "$1" 2>/dev/null
}
check_mouse_movement() {
    current_pos=$(xdotool getmouselocation --shell)

    # Calculate the distance moved by the mouse
    distance=$(echo "sqrt((${current_pos%X}-$initial_pos_X)^2 + (${current_pos%Y}-$initial_pos_Y)^2)" | bc)

    # Check if the distance moved exceeds a specific amount
    if (( $(echo "$distance > $max_distance" | bc -l) ))
    then
        echo "Mouse movement detected. Stopping..."
        exit 1
    fi
}


# kill just in case was already running
killall rec >/dev/null 2>&1

# start recording
record $FILE

# give time to the user to position the cursor
sleep 1

# yad form
input=$(yad \
    --form \
    --title "Yad Sound Recorder" \
    --field "ChatGPT instruction" \
    --on-top \
    --button="STOP!gtk-media-stop":0
    )
echo "Exit yad\nChatGPT instruction: $input"

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
# sox $FILE "unsilenced_$FILE" silence -l 1 0.1 1% -1 0.3 1%
rm /tmp/tmpoutput*.mp3
sox $FILE /tmp/tmpoutput.mp3 silence 1 1 0.1% 1 1 0.1% : newfile : restart
cat /tmp/tmpoutput*.mp3 > "/tmp/unsilenced_$FILE"
rm /tmp/tmpout*.mp3
$FILE="unsilenced_$FILE"
echo "Removed silence, new file is $FILE"

# record mouse position
initial_pos=$(xdotool getmouselocation --shell)

echo "Calling whisper"
text=$(openai api audio.transcribe --model whisper-1 --response-format text --temperature 0 -f $FILE  --language $LANG --prompt "$PROMPT")
echo "Whisper transcript: $text"

if [[ ! -z $input ]]
then
    echo "Calling ChatGPT with instruction $input"
    text=$(openai api chat_completions.create --model gpt-3.5-turbo -g system "$input" -g user "$text")
    echo "ChatGPT output: $text"
else
    echo "Not using ChatGPT"
fi

function replace_char() {
    local -A replace_table
    replace_table=(é eacute à agrave è egrave ç ccedilla " " space â acircumflex "'" apostrophe "\n" Return "\r" Return % percent - minus ô ocircumflex ê ecircumflex ù ugrave î icircumflex "," comma "." period "?" question "!" exclam "*" asterisk ":" colon ";" semicolon û ucircumflex)
    if [[ -n ${replace_table[$1]} ]]; then
        echo ${replace_table[$1]}
    else
        echo $1
    fi
}


i=1
while (( i <= ${#text} ))
do
    # every few character check if the mouse moved
    if (( i % 5 == 0 ))
    then
        check_mouse_movement
    fi

    # type character
    current_char=${text[$i]}

    # replace character by xdotool friendly alternative if possible
    current_char=$(replace_char "$current_char")

    type_input "$current_char"
    (( i++ ))
done

