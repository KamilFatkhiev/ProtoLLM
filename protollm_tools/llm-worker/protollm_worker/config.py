import os


class Config:
    def __init__(
            self,
            redis_host: str = "localhost",
            redis_port: int = 6379,
            redis_prefix: str = "llm-api",
            rabbit_host: str = "localhost",
            rabbit_port: int = 5672,
            rabbit_login: str = "admin",
            rabbit_password: str = "admin",
            queue_name: str = "llm-api-queue",
            model_path: str = None,
            token_len: int = None,
            tensor_parallel_size: int = None,
            gpu_memory_utilisation: float = None,
    ):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_prefix = redis_prefix
        self.rabbit_host = rabbit_host
        self.rabbit_port = rabbit_port
        self.rabbit_login = rabbit_login
        self.rabbit_password = rabbit_password
        self.queue_name = queue_name
        self.model_path = model_path,
        self.token_len = token_len,
        self.tensor_parallel_size = tensor_parallel_size,
        self.gpu_memory_utilisation = gpu_memory_utilisation,

    @classmethod
    def read_from_env(cls) -> 'Config':
        return Config(
            os.environ.get("REDIS_HOST", "localhost"),
            os.environ.get("REDIS_PORT", "6379"),
            os.environ.get("REDIS_PREFIX", "llm-api"),
            os.environ.get("RABBIT_MQ_HOST", "localhost"),
            os.environ.get("RABBIT_MQ_PORT", "5672"),
            os.environ.get("RABBIT_MQ_LOGIN", "admin"),
            os.environ.get("RABBIT_MQ_PASSWORD", "admin"),
            os.environ.get("QUEUE_NAME", "llm-api-queue"),
            os.environ.get("MODEL_PATH"),
            int(os.environ.get("TOKENS_LEN", "16384")),
            int(os.environ.get("TENSOR_PARALLEL_SIZE", "2")),
            float(os.environ.get("GPU_MEMORY_UTILISATION", "0.9")),
        )

    @classmethod
    def read_from_env_file(cls, path: str) -> 'Config':
        with open(path) as file:
            lines = file.readlines()
        env_vars = {}
        for line in lines:
            key, value = line.split("=")
            env_vars[key] = value
        return Config(
            env_vars.get("REDIS_HOST", "localhost"),
            int(env_vars.get("REDIS_PORT", "6379")),
            env_vars.get("REDIS_PREFIX", "llm-api"),
            env_vars.get("RABBIT_MQ_HOST", "localhost"),
            int(env_vars.get("RABBIT_MQ_PORT", "5672")),
            env_vars.get("RABBIT_MQ_LOGIN", "admin"),
            env_vars.get("RABBIT_MQ_PASSWORD", "admin"),
            env_vars.get("QUEUE_NAME", "llm-api-queue"),
            env_vars.get("MODEL_PATH"),
            int(env_vars.get("TOKENS_LEN", "16384")),
            int(env_vars.get("TENSOR_PARALLEL_SIZE", "2")),
            float(env_vars.get("GPU_MEMORY_UTILISATION", "0.9")),
        )