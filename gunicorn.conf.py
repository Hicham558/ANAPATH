import multiprocessing

bind = "0.0.0.0:10000"
workers = 1  # Important : 1 seul worker sur free tier
worker_class = "sync"
timeout = 120
keepalive = 5
max_requests = 500
max_requests_jitter = 50
preload_app = True  # Charge l'app avant de forker les workers
