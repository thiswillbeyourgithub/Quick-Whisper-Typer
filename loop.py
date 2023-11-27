import threading
import sys
import queue
import time
from pynput import keyboard

from quick_whisper_typer import main

# source: https://pypi.org/project/pynput/

if "verbose" in sys.argv:
    def p(s):
        print(s)
else:
    def p(s):
        pass


class Buffer:
    buff = []
    started = 0
    q = queue.Queue()
    listening = False

def on_press(key):
    if key == shift:
        b.started = time.time()
        p("Pressed shift")

def on_release(key):
    if key == shift:
        p("Released shift")
        if b.listening:
            p("Stopped thread")
            b.q.put("STOP")
            b.listening = False
            return

        p(len(b.buff))
        p(time.time() - b.started)
        if len(b.buff) >= 3 and time.time() - b.started > long_press:
            p("Started voice chat")
            thread = threading.Thread(
                    target=main,
                    kwargs={
                        "lang": "fr",
                        "task": "new_voice_chat",
                        "voice_engine": "openai",
                        "daemon_mode": b.q,
                        },
                    daemon=True,
                    )
            thread.start()
            b.listening = True
            b.buff = []
        elif len(b.buff) >= 2 and time.time() - b.started > long_press:
            p("Continuing voice chat")
            thread = threading.Thread(
                    target=main,
                    kwargs={
                        "lang": "fr",
                        "task": "continue_voice_chat",
                        "voice_engine": "openai",
                        "daemon_mode": b.q,
                        },
                    daemon=True,
                    )
            thread.start()
            b.listening = True
            b.buff = []

        # remove if too old
        if b.buff:
            current = time.time()
            b.buff = [t for t in b.buff if current - t <= buff_size_second]

        b.buff.append(time.time())


    else:
        b.buff = []

shift = keyboard.Key.shift
b = Buffer()
long_press = 1
buff_size_second = 1

if __name__ == "__main__":
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()  # non blocking
    #listener.join()
    #time.sleep(60*60)
    while True:
        pass
        #time.sleep(0.01)

