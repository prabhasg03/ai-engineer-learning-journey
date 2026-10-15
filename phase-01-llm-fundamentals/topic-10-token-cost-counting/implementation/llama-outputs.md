```cmd
C:\Users\Hp>llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M -ngl 0 -c 4096 --host 127.0.0.1 --port 8080
0.00.001.285 I srv  llama_server: initializing ...
0.00.712.978 I cmn  common_param: common_params_print_info: verbosity = 3 (adjust with the `-lv N` CLI arg)
0.00.713.438 W srv  llama_server: security: no API key is set and CORS allows all origins (see https://github.com/ggml-org/llama.cpp/pull/25655)
0.00.721.529 I srv    load_model: loading model 'Qwen/Qwen3-4B-GGUF:Q4_K_M'
0.01.368.883 W load: control-looking token: 128247 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.06.227.509 I cmn          init: llama threadpool init, n_threads = 4
0.07.280.945 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
0.07.341.331 I srv  llama_server: model loaded
0.07.341.641 I srv  llama_server: listening on http://127.0.0.1:8080
0.07.341.647 W srv  llama_server: notice: server default port will be changed to :9931 in a future release (ref: https://github.com/ggml-org/llama.cpp/pull/26508)
0.10.885.564 I slot get_availabl: id  3 | task -1 | selected slot by LRU, t_last = -1
0.10.888.458 I slot launch_slot_: id  3 | task 0 | processing task, is_child = 0
0.16.917.957 I slot print_timing: id  3 | task 0 | prompt eval time =    1951.81 ms /    23 tokens (   84.86 ms per token,    11.78 tokens per second)
0.16.917.984 I slot print_timing: id  3 | task 0 |        eval time =    4077.20 ms /    27 tokens (  156.82 ms per token,     6.38 tokens per second)
0.16.917.993 I slot print_timing: id  3 | task 0 |       total time =    6029.00 ms /    50 tokens
0.16.918.005 I slot print_timing: id  3 | task 0 |    graphs reused =         26
0.16.919.686 I slot      release: id  3 | task 0 | stop processing: n_tokens = 49, truncated = 0
```