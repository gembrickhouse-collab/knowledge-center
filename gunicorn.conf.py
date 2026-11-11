import os
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
timeout = 150
graceful_timeout = 30
workers = 1
threads = 4

def post_worker_init(worker):
    import app as _app
    _app.ensure_scheduler_started()
