```cmd
C:\Users\Hp>llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M -ngl 0 -c 4096 --host 127.0.0.1 --port 8080
0.00.001.110 I srv  llama_server: initializing ...
0.00.741.604 I cmn  common_param: common_params_print_info: verbosity = 3 (adjust with the `-lv N` CLI arg)
0.00.741.981 W srv  llama_server: security: no API key is set and CORS allows all origins (see https://github.com/ggml-org/llama.cpp/pull/25655)
0.00.753.775 I srv    load_model: loading model 'Qwen/Qwen3-4B-GGUF:Q4_K_M'
0.01.399.625 W load: control-looking token: 128247 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.07.971.606 I cmn          init: llama threadpool init, n_threads = 4
0.08.986.198 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
0.09.051.678 I srv  llama_server: model loaded
0.09.052.009 I srv  llama_server: listening on http://127.0.0.1:8080
0.09.052.016 W srv  llama_server: notice: server default port will be changed to :9931 in a future release (ref: https://github.com/ggml-org/llama.cpp/pull/26508)
0.29.674.758 I slot get_availabl: id  3 | task -1 | selected slot by LRU, t_last = -1
0.29.682.721 I slot launch_slot_: id  3 | task 0 | processing task, is_child = 0
0.39.524.642 I slot print_timing: id  3 | task 0 | prompt eval time =    1235.44 ms /    34 tokens (   36.34 ms per token,    27.52 tokens per second)
0.39.524.675 I slot print_timing: id  3 | task 0 |        eval time =    8601.86 ms /    28 tokens (  318.59 ms per token,     3.14 tokens per second)
0.39.525.449 I slot print_timing: id  3 | task 0 |       total time =    9837.30 ms /    62 tokens
0.39.525.455 I slot print_timing: id  3 | task 0 |    graphs reused =         27
0.39.540.057 I slot      release: id  3 | task 0 | stop processing: n_tokens = 61, truncated = 0
0.39.796.573 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.611 (> 0.100 thold), f_keep = 0.361
0.39.812.939 I slot launch_slot_: id  3 | task 29 | processing task, is_child = 0
0.44.167.438 I slot print_timing: id  3 | task 29 | prompt eval time =    1384.72 ms /    14 tokens (   98.91 ms per token,    10.11 tokens per second)
0.44.167.447 I slot print_timing: id  3 | task 29 |        eval time =    2969.02 ms /    20 tokens (  156.26 ms per token,     6.40 tokens per second)
0.44.167.450 I slot print_timing: id  3 | task 29 |       total time =    4353.74 ms /    34 tokens
0.44.167.452 I slot print_timing: id  3 | task 29 |    graphs reused =         45
0.44.168.680 I slot      release: id  3 | task 29 | stop processing: n_tokens = 55, truncated = 0
0.44.273.785 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.286 (> 0.100 thold), f_keep = 0.400
0.44.282.271 I slot launch_slot_: id  3 | task 50 | processing task, is_child = 0
0.50.414.229 I slot print_timing: id  3 | task 50 | prompt eval time =     914.26 ms /    47 tokens (   19.45 ms per token,    51.41 tokens per second)
0.50.414.240 I slot print_timing: id  3 | task 50 |        eval time =    5217.64 ms /    33 tokens (  163.05 ms per token,     6.13 tokens per second)
0.50.414.242 I slot print_timing: id  3 | task 50 |       total time =    6131.90 ms /    80 tokens
0.50.414.243 I slot print_timing: id  3 | task 50 |    graphs reused =         76
0.50.415.337 I slot      release: id  3 | task 50 | stop processing: n_tokens = 109, truncated = 0
0.51.085.976 I slot get_availabl: id  2 | task -1 | selected slot by LRU, t_last = -1
0.51.087.030 I slot launch_slot_: id  2 | task 84 | processing task, is_child = 0
0.59.281.312 I slot print_timing: id  2 | task 84 | prompt eval time =    3805.93 ms /   304 tokens (   12.52 ms per token,    79.88 tokens per second)
0.59.281.325 I slot print_timing: id  2 | task 84 |        eval time =    4351.17 ms /    26 tokens (  174.05 ms per token,     5.75 tokens per second)
0.59.282.117 I slot print_timing: id  2 | task 84 |       total time =    8157.11 ms /   330 tokens
0.59.282.126 I slot print_timing: id  2 | task 84 |    graphs reused =        100
0.59.285.934 I slot      release: id  2 | task 84 | stop processing: n_tokens = 329, truncated = 0
```