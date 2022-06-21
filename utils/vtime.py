import time
import yaml
import logging

TIME_DILATION = None

def get_time_dilation():
    global TIME_DILATION
    if not TIME_DILATION:
        with open("config.yaml", "r") as f_in:
            vsnet_config = yaml.safe_load(f_in).get("vsnet", {})
            TIME_DILATION = vsnet_config.get("time_dilation", 1.0)

    return TIME_DILATION

def now():
    return get_time_dilation()*(time.time_ns()/10**9)

def time_this(func):
    def timed_func(*args, **kwargs):
        start_time = now()
        result = func(*args, **kwargs)
        end_time = now()
        logging.debug(f"Ran {func.__name__} in {end_time - start_time} virtual seconds")
        return result

    return timed_func
