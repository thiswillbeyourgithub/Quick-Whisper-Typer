#!/usr/bin/zsh

# set -euxo pipefail

# Parsing command line arguments as an array
LANG=""
PROMPT=""
TASK=""

# pre defined prompts
declare -A prompts
prompts[fr]="Dictee vocale sur mon telephone: "
prompts[en]="Dictation on my smartphone: "

# pre defined system prompts
declare -A system_prompts
system_prompts[vocal]="You are a helpful assistant. I am in a hurry and your answers will be played on speaker so use as few words as you can while remaining helpful and truthful. Don't use too short sentences otherwise the speakers will crash."
system_prompts[transform_clipboard]="You transform INPUT_TEXT according to an instruction. Only reply the transformed text without anything else."

# pre defined vocal models
declare -A speaker_models
speaker_models[fr]="fr_FR-gilles-low"
speaker_models[en]="en_US-lessac-medium"

# load openai api key
cd "$(dirname "$0")"
export OPENAI_API_KEY=$(cat ./API_KEY.txt)

# vars
FILE="/tmp/quick_whisper_audio_$(date +%s).mp3"
start_time=$(date +%s)
min_duration=2  # if the recording is shorter, exit

# functions
log() {
    echo $1
    echo "$(date +%s) $1" >> ./texts.log
}
record() {
    log "Recording $1"
    rec -r 44000 -c 1 -b 16 "$1" &
}


# gather user arguments
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
        -t | --task)
            TASK="$2"
            shift 2
            ;;
        #*)
        #    echo "Invalid option: $arg"
        #    exit 1
        #    ;;
    esac
done

# check if the language is supplied and correct
allowed_langs=("fr" "en")
if [[ -z "$LANG" || ! " ${allowed_langs[@]}  " =~ " $LANG " ]]
then
    echo "Invalid lang $LANG not part of $allowed_langs"
    exit 1
fi
speaker_model="${speaker_models[$LANG]}"

# selecting prompt based on lang
if [[ -z "$PROMPT" ]]
then
    PROMPT="${prompts[$LANG]}"
fi

# checking that the task is allowed
allowed_tasks=("transform_clipboard" "new_vocal_chat" "continue_vocal_chat" "write")
if [[ -z "$TASK" || ! " ${allowed_tasks[@]}  " =~ " $TASK " ]]
then
    echo "Invalid task $TASK not part of $allowed_tasks"
    exit 1
fi

# check that the clipboard is not empty
prev_clipboard=$(xclip -o -sel clipboard)
if [[ $TASK == "transform_clipboard" ]]
then
    if [[ -z "$prev_clipboard" ]]
    then
        log "Clipboard is empty, this is not compatible with $task"
        exit 1
    fi
fi

# telling user that everything worked
log "\n"
log "\n"
log "Will use language $LANG and prompt $PROMPT and task $TASK "

# kill just in case rec was already running
killall rec >/dev/null 2>&1

# start recording
record $FILE

# give time to the user to position the cursor
# sleep 1

# yad form
transf_instruct=$(yad \
    --form \
    --title "Yad Sound Recorder" \
    --text "TASK: $TASK\nLANG: $LANG" \
    --field "Whisper prompt" "$PROMPT" \
    --field "ChatGPT instruction" "" \
    --on-top \
    --button="gtk-cancel:1" \
    --button="Go!gtk-media-stop:0" \
    --default-button=0
    )
    #
# if pressed cancel or escape: exit
if [[ -z $transf_instruct ]]
then
    killall rec
    log "Pressed cancel or escape. Exiting."
    exit
fi

log "\nChatGPT instruction: $transf_instruct for task $TASK"

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

# # removing silences longer than Xs
# rm /tmp/tmpoutput*.mp3
# sox $FILE /tmp/tmpoutput.mp3 silence 1 1 0.1% 1 1 0.1% : newfile : restart
# cat /tmp/tmpoutput*.mp3 > "/tmp/unsilenced_$FILE"
# rm /tmp/tmpout*.mp3
# $FILE="unsilenced_$FILE"
# log "Removed silence, new file is $FILE"

log "Calling whisper"
text=$(openai api audio.transcribe --model whisper-1 --response-format text --temperature 0 -f $FILE  --language $LANG --prompt "$PROMPT")
log "Whisper transcript: $text"

if [[ $TASK == "transform_clipboard" ]]
    then
    log "Calling ChatGPT with instruction \"$transf_instruct\" and tasked to transform the clipboard"
    log "Previous clipboard: $prev_clipboard"
    text=$(openai api chat_completions.create --model gpt-3.5-turbo-1106 -g system ${system_prompts[transform_clipboard]} -g user "INPUT_TEXT: '$prev_clipboard'\n\nINSTRUCTION: '$text'")
    log "ChatGPT clipboard transformation: \"$text\""

elif [[ $TASK == "new_vocal_chat" ]] || [[ $TASK == "continue_vocal_chat" ]]
then

    if [[ $TASK == "new_vocal_chat" ]]
    then
        VOCAL_FILE="/tmp/quick_whisper_chat_$(date +%s).txt"
        log "Creating new vocal chat file: $VOCAL_FILE"
        message_arg=""

    else
        VOCAL_FILE=$(\ls -t /tmp/quick_whisper_chat_* | head -1)
        log "Reusing previous vocal chat file: $VOCAL_FILE"

        # read the previous message list
        messages=()
        IFS="#####"
        while IFS= read -r line; do
            messages+=("$line")
        done < $VOCAL_FILE

        # parse the message as a long arg string
        message_arg=""
        for element in "${messages[@]}"; do
            read -r -a fields <<< "$element"
            for ((i = 0; i < ${#fields[@]}; i++)); do
                if ((i % 2 == 0)); then
                    role="user"
                else
                    role="assistant"
                fi
                message_arg+="-g $role \"${fields[i]}\" "
            done
        done

    fi

    answer=$(openai api chat_completions.create --model gpt-3.5-turbo-1106 -g system ${system_prompts[vocal]} $message_arg -g "user" "$text")
    log "ChatGPT answer to the chat: \"$answer\""

    # add text and answer to the file
    echo "\n#####\n" >> $VOCAL_FILE
    echo $text >> $VOCAL_FILE
    echo "\n#####\n" >> $VOCAL_FILE
    echo $answer >> $VOCAL_FILE

    # play vocal file
    VOCAL_FILE_MP3="/tmp/quick_whisper_piper_$(date +%s).mp3"
    log "storing vocal mp3 to $VOCAL_FILE_MP3"
    echo "$answer" | python -m piper --model $speaker_model --output_file $VOCAL_FILE_MP3 2&>1
    mplayer -really-quiet $VOCAL_FILE_MP3 2&>1
    log "done playing vocal file"

    exit
fi

if [[ ! -z $transf_instruct ]]
then
    log "Calling ChatGPT with instruction $transf_instruct"
    text=$(openai api chat_completions.create --model gpt-3.5-turbo-1106 -g system ${system_prompts[transform_clipboard]} -g user "INPUT_TEXT: '$text'\n\nINSTRUCTION: '$transf_instruct'")
    log "ChatGPT output: $text"
else
    log "Not using ChatGPT"
fi


# save to all clipboard just in case
log "using clipboard to write"
echo "$text" | xclip -sel primary
echo "$text" | xclip -sel secondary
echo "$text" | xclip -sel clipoard
xdotool key ctrl+v
echo "$prev_clipboard" | xclip -sel clipboard
