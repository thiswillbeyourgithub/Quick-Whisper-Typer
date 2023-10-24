#!/usr/bin/zsh

# set -euxo pipefail

LANG=$1
allowed_langs=("fr" "en")
if [[ -z "$LANG" || ! " ${allowed_langs[@]}  " =~ " $LANG " ]]
then
    echo "Invalid lang $LANG"
    exit 1
fi

FILE="/tmp/audio_recording_$(date +%s).mp3"
cd "$(dirname "$0")"
export OPENAI_API_KEY=$(cat ./API_KEY.txt)
start_time=$(date +%s)
min_duration=1
max_distance=10

record() {
    echo "Recording $1"
    rec -r 44000 -c 1 -b 16 "$1" &
}
type_input() {
    xdotool type --delay 0 "$1" 2>/dev/null
}
check_mouse_movement() {
    current_pos=$(xdotool getmouselocation --shell 2>/dev/null) 2>/dev/null

    # Calculate the distance moved by the mouse
    distance=$(echo "sqrt((${current_pos%X}-$initial_pos_X)^2 + (${current_pos%Y}-$initial_pos_Y)^2)" | bc) 2>/dev/null

    # Check if the distance moved exceeds a specific amount
    if (( $(echo "$distance > $max_distance" | bc -l) )); then
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

# create a form, will keep going after exiting
input=$(yad \
    --form \
    --title "Yad Sound Recorder" \
    --on-top \
    --button="STOP!gtk-media-stop":0
    )

echo "Exit yad: $input"

# kill the recording
killall rec >/dev/null 2>&1
echo "Done recording"

end_time=$(date +%s)
duration=$((end_time - start_time))
echo "Duration $duration"

if (( duration < min_duration ))
then
    echo "Recording too short, exiting without calling whisper."
    sleep 1
    echo ""
    exit 0
fi


# echo "playing file"
# mplayer $FILE

initial_pos=$(xdotool getmouselocation --shell)

echo "Calling whisper"
text=$(openai api audio.transcribe --model whisper-1 --response-format text --temperature 0 -f $FILE  --language $LANG --prompt "Note vocale pour mon assistant : ")
echo "Whisper text: $text"

# echo "Calling chatgpt"
# text=$(echo "$text" | llm "traduit ce texte en anglais")
# echo "ChatGPT text: $text"

# make sure to use french keyboard
setxkbmap fr

i=1
while (( i <= ${#text} ))
do
    # type character
    current_char=${text[$i]}
    type_input "$current_char"
    (( i++ ))

    # every few character check if the mouse moved
    if (( i % 5 == 0 ))
    then
        check_mouse_movement
    fi
done

