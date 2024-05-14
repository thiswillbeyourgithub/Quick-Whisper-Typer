import os
from plyer import notification
import fire
import time
from pynput import keyboard

from quick_whisper_typer import QuickWhisper

# source: https://pypi.org/project/pynput/

shift = keyboard.Key.shift

class Buffer:
    buff = []
    started = 0
    listening = False

class Loop:
    b = Buffer()

    def __init__(
        self,
        shift_number: int = 4,
        purge_time: int = 4,
        verbose: bool = False,

        sound_cleanup=None,
        whisper_lang=None,
        auto_paste=None,
        voice_engine=None,
        piper_model_path=None,
        gui=None,
        ):
        """
        Parameters
        ----------
        shift_number: int, default 4
            number of  times you have to press shift for the loop to trigger

        purge_time: int, default 4
            every that much time, the number of shift counted will be reset
            (rolling window)

        verbose: bool, default False

        for all other arguments see:
            see quick_whisper_typer.py --help

        """
        self.shift_number = shift_number
        self.purge_time = purge_time
        self.verbose = verbose
        self.voice_engine = voice_engine
        self.auto_paste = auto_paste
        self.whisper_lang = whisper_lang
        self.sound_cleanup = sound_cleanup
        self.piper_model_path = piper_model_path
        self.gui = gui

        self.waiting_for_letter = False

        listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release,
        )
        listener.start()  # non blocking
        while True:
            pass
            #time.sleep(0.01)


    def on_press(self, key):
        if key == shift:
            self.b.started = time.time()
            # self.log("Pressed shift")

    def on_release(self, key):
        if key == shift:
            self.log("Released shift")
            if self.b.listening:
                self.log("Stopped the quickwhisper process")
                self.b.listening = False
                return

            self.log(f"Shift counter: {len(self.b.buff)}")

            self.b.buff.append(time.time())

            if len(self.b.buff) >= self.shift_number:
                self.waiting_for_letter = True
                self.notif("Waiting for task letter w(rite), n(ewvoice), c(ontinue voice), t(ransform_clipboard)")

            # remove if too old
            self.b.buff = [t for t in self.b.buff if time.time() - t <= self.purge_time]


        elif self.waiting_for_letter:
            if not hasattr(key, "char"):
                self.b.waiting_for_letter = False
                self.b.buff = []
                return

            if key.char not in ["w", "n", "c", "t"]:
                self.notif(f"Key pressed not part of task letter: w(rite), n(ewvoice), c(ontinue voice), t(ransform_clipboard): {key.char}")
                self.b.waiting_for_letter = False
                self.b.buff = []
                return

            kwargs = {
                "voice_engine": self.voice_engine,
                "verbose": self.verbose,
                "auto_paste": self.auto_paste,
                "sound_cleanup": self.sound_cleanup,
                "whisper_lang": self.whisper_lang,
                "piper_model_path": self.piper_model_path,
                "gui": self.gui,
            }
            if key.char == "n":
                self.notif("Started voice chat")
                kwargs["task"] = "new_voice_chat"

            elif key.char == "c":
                self.notif("Continuing voice chat")
                kwargs["task"] = "continue_voice_chat"

            elif key.char == "w":
                self.notif("writing mode")
                kwargs["task"] = "write"

            elif key.char == "t":
                self.notif("transform_clipboard mode")
                kwargs["task"] = "transform_clipboard"

            else:
                self.notif(f"Unexpected key pressed: {key}")
                raise ValueError(key)

            QuickWhisper(**kwargs)
            self.b.listening = True
            self.b.buff = []
            self.waiting_for_letter = False
        else:
            self.b.buff = []
            self.log(f"Pressed: {key}")

    @classmethod
    def notif(self, message: str) -> str:
        print(message)
        notification.notify(title="Quick Whisper (Loop)", message=message, timeout=-1)

    def log(self, message):
        if self.verbose:
            print(message)

if __name__ == "__main__":
    args, kwargs = fire.Fire(lambda *args, **kwargs: [args, kwargs])
    if args:
        raise Exception(f"Non keyword args are not supported: {args}")
    if "help" in kwargs:
        print(help(Loop))
        raise SystemExit()

    try:
        Loop(**kwargs)
    except Exception as err:
        os.system("killall rec")
        Loop.notif(essage=f"Error in loop: '{err}'", timeout=-1)
        raise
