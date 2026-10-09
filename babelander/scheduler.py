"""Bounded priority scheduler: one model worker, exceptions finish futures."""
from concurrent.futures import Future
import heapq
import itertools
import threading

from .types import Mode

PRIORITIES = {Mode.DIALOG:0, Mode.REPLY:1, Mode.CHAT:1, Mode.EQUIPMENT:2, Mode.QUEST:2, Mode.SCREEN:2}


class Scheduler:
    def __init__(self, capacity=128, workers=1):
        self.capacity = capacity
        self.condition = threading.Condition()
        self.pending = []
        self.sequence = itertools.count()
        self.closed = False
        self.threads = [threading.Thread(target=self._run, name='Babelander2-inference', daemon=True) for _ in range(workers)]
        for thread in self.threads:
            thread.start()

    def submit(self, mode, function, cancelled=lambda: False):
        future = Future()
        with self.condition:
            if self.closed:
                raise RuntimeError('翻譯服務已關閉。')
            kept = []
            for entry in self.pending:
                try:
                    obsolete = entry[4]()
                except BaseException as error:
                    if entry[2].set_running_or_notify_cancel():
                        entry[2].set_exception(error)
                    continue
                if obsolete or entry[2].cancelled():
                    entry[2].cancel()
                else:
                    kept.append(entry)
            self.pending = kept
            heapq.heapify(self.pending)
            if len(self.pending) >= self.capacity:
                raise RuntimeError('等待翻譯已滿，請稍後重試。')
            heapq.heappush(self.pending,(PRIORITIES[mode],next(self.sequence),future,function,cancelled))
            self.condition.notify()
        return future

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.closed)
                if not self.pending:
                    return
                _,_,future,function,cancelled = heapq.heappop(self.pending)
            try:
                if cancelled():
                    future.cancel()
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    future.set_result(function())
                except BaseException as error:
                    future.set_exception(error)
            except BaseException as error:
                if future.set_running_or_notify_cancel():
                    future.set_exception(error)

    def close(self):
        with self.condition:
            self.closed = True
            for entry in self.pending:
                entry[2].cancel()
            self.pending.clear()
            self.condition.notify_all()

    def join(self, timeout=5):
        for thread in self.threads:
            thread.join(timeout)
