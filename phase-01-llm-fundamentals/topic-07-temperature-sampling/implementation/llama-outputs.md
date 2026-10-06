```
C:\Users\Hp>llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M -ngl 0 -c 4096 --host 127.0.0.1 --port 8080
0.00.001.070 I srv  llama_server: initializing ...
0.01.255.323 I cmn  common_param: common_params_print_info: verbosity = 3 (adjust with the `-lv N` CLI arg)
0.01.255.836 W srv  llama_server: security: no API key is set and CORS allows all origins (see https://github.com/ggml-org/llama.cpp/pull/25655)
0.01.263.985 I srv    load_model: loading model 'Qwen/Qwen3-4B-GGUF:Q4_K_M'
0.02.024.190 W load: control-looking token: 128247 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.08.366.725 I cmn          init: llama threadpool init, n_threads = 4
0.09.697.917 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
0.09.755.688 I srv  llama_server: model loaded
0.09.756.057 I srv  llama_server: listening on http://127.0.0.1:8080
0.09.756.066 W srv  llama_server: notice: server default port will be changed to :9931 in a future release (ref: https://github.com/ggml-org/llama.cpp/pull/26508)
0.31.632.210 I slot get_availabl: id  3 | task -1 | selected slot by LRU, t_last = -1
0.31.638.244 I slot launch_slot_: id  3 | task 0 | processing task, is_child = 0
0.53.799.503 I slot print_timing: id  3 | task 0 | n_gen =    100, tg =   5.10 t/s, tg_3s =   5.15 t/s
0.56.932.870 I slot print_timing: id  3 | task 0 | n_gen =    119, tg =   5.23 t/s, tg_3s =   6.06 t/s
1.00.074.683 I slot print_timing: id  3 | task 0 | n_gen =    133, tg =   5.14 t/s, tg_3s =   4.46 t/s
1.03.117.921 I slot print_timing: id  3 | task 0 | prompt eval time =    2745.05 ms /    24 tokens (  114.38 ms per token,     8.74 tokens per second)
1.03.117.940 I slot print_timing: id  3 | task 0 |        eval time =   28732.76 ms /   150 tokens (  192.84 ms per token,     5.19 tokens per second)
1.03.118.342 I slot print_timing: id  3 | task 0 |       total time =   31477.82 ms /   174 tokens
1.03.118.667 I slot print_timing: id  3 | task 0 |    graphs reused =        149
1.03.124.995 I slot      release: id  3 | task 0 | stop processing: n_tokens = 173, truncated = 0
1.03.622.025 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
1.03.638.096 I slot launch_slot_: id  3 | task 151 | processing task, is_child = 0
1.03.638.686 W slot   operator(): id  3 | task 151 | need to evaluate at least 1 token for each active slot (n_past = 24, task.n_tokens() = 24)
1.03.638.691 W slot   operator(): id  3 | task 151 | n_past was set to 23
1.22.610.382 I slot print_timing: id  3 | task 151 | n_gen =    100, tg =   5.28 t/s, tg_3s =   5.33 t/s
1.25.670.145 I slot print_timing: id  3 | task 151 | n_gen =    114, tg =   5.18 t/s, tg_3s =   4.57 t/s
1.28.809.513 I slot print_timing: id  3 | task 151 | n_gen =    134, tg =   5.33 t/s, tg_3s =   6.37 t/s
1.31.222.863 I slot print_timing: id  3 | task 151 | prompt eval time =     217.97 ms /     1 tokens (  217.97 ms per token,     4.59 tokens per second)
1.31.222.876 I slot print_timing: id  3 | task 151 |        eval time =   27365.54 ms /   150 tokens (  183.66 ms per token,     5.44 tokens per second)
1.31.223.232 I slot print_timing: id  3 | task 151 |       total time =   27583.52 ms /   151 tokens
1.31.223.526 I slot print_timing: id  3 | task 151 |    graphs reused =        299
1.31.229.110 I slot      release: id  3 | task 151 | stop processing: n_tokens = 173, truncated = 0
1.31.337.772 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
1.31.351.729 I slot launch_slot_: id  3 | task 302 | processing task, is_child = 0
1.31.352.424 W slot   operator(): id  3 | task 302 | need to evaluate at least 1 token for each active slot (n_past = 24, task.n_tokens() = 24)
1.31.352.429 W slot   operator(): id  3 | task 302 | n_past was set to 23
1.49.604.057 I slot print_timing: id  3 | task 302 | n_gen =    100, tg =   5.47 t/s, tg_3s =   5.52 t/s
1.52.740.554 I slot print_timing: id  3 | task 302 | n_gen =    116, tg =   5.41 t/s, tg_3s =   5.10 t/s
1.55.866.811 I slot print_timing: id  3 | task 302 | n_gen =    122, tg =   4.96 t/s, tg_3s =   1.92 t/s
1.58.871.670 I slot print_timing: id  3 | task 302 | n_gen =    139, tg =   5.04 t/s, tg_3s =   5.65 t/s
2.00.711.251 I slot print_timing: id  3 | task 302 | prompt eval time =     136.42 ms /     1 tokens (  136.42 ms per token,     7.33 tokens per second)
2.00.711.304 I slot print_timing: id  3 | task 302 |        eval time =   29221.87 ms /   150 tokens (  196.12 ms per token,     5.10 tokens per second)
2.00.711.781 I slot print_timing: id  3 | task 302 |       total time =   29358.28 ms /   151 tokens
2.00.712.305 I slot print_timing: id  3 | task 302 |    graphs reused =        449
2.00.718.092 I slot      release: id  3 | task 302 | stop processing: n_tokens = 173, truncated = 0
2.00.821.273 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
2.00.835.143 I slot launch_slot_: id  3 | task 453 | processing task, is_child = 0
2.00.835.796 W slot   operator(): id  3 | task 453 | need to evaluate at least 1 token for each active slot (n_past = 24, task.n_tokens() = 24)
2.00.835.802 W slot   operator(): id  3 | task 453 | n_past was set to 23
2.16.534.371 I slot print_timing: id  3 | task 453 | n_gen =    100, tg =   6.36 t/s, tg_3s =   6.42 t/s
2.19.661.436 I slot print_timing: id  3 | task 453 | n_gen =    118, tg =   6.26 t/s, tg_3s =   5.76 t/s
2.22.884.197 I slot print_timing: id  3 | task 453 | n_gen =    133, tg =   6.02 t/s, tg_3s =   4.65 t/s
2.25.895.598 I slot print_timing: id  3 | task 453 | n_gen =    148, tg =   5.90 t/s, tg_3s =   4.98 t/s
2.26.257.964 I slot print_timing: id  3 | task 453 | prompt eval time =     130.08 ms /     1 tokens (  130.08 ms per token,     7.69 tokens per second)
2.26.258.026 I slot print_timing: id  3 | task 453 |        eval time =   25291.23 ms /   150 tokens (  169.74 ms per token,     5.89 tokens per second)
2.26.258.430 I slot print_timing: id  3 | task 453 |       total time =   25421.31 ms /   151 tokens
2.26.258.720 I slot print_timing: id  3 | task 453 |    graphs reused =        599
2.26.264.044 I slot      release: id  3 | task 453 | stop processing: n_tokens = 173, truncated = 0
2.26.492.560 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
2.26.516.980 I slot launch_slot_: id  3 | task 604 | processing task, is_child = 0
2.26.518.292 W slot   operator(): id  3 | task 604 | need to evaluate at least 1 token for each active slot (n_past = 24, task.n_tokens() = 24)
2.26.518.301 W slot   operator(): id  3 | task 604 | n_past was set to 23
2.43.693.307 I slot print_timing: id  3 | task 604 | n_gen =    100, tg =   5.84 t/s, tg_3s =   5.90 t/s
2.46.783.468 I slot print_timing: id  3 | task 604 | n_gen =    116, tg =   5.74 t/s, tg_3s =   5.18 t/s
2.49.951.629 I slot print_timing: id  3 | task 604 | n_gen =    133, tg =   5.68 t/s, tg_3s =   5.36 t/s
2.53.054.908 I slot print_timing: id  3 | task 604 | n_gen =    149, tg =   5.62 t/s, tg_3s =   5.16 t/s
2.53.344.639 I slot print_timing: id  3 | task 604 | prompt eval time =     214.56 ms /     1 tokens (  214.56 ms per token,     4.66 tokens per second)
2.53.344.649 I slot print_timing: id  3 | task 604 |        eval time =   26611.84 ms /   150 tokens (  178.60 ms per token,     5.60 tokens per second)
2.53.345.199 I slot print_timing: id  3 | task 604 |       total time =   26826.39 ms /   151 tokens
2.53.345.437 I slot print_timing: id  3 | task 604 |    graphs reused =        749
2.53.350.388 I slot      release: id  3 | task 604 | stop processing: n_tokens = 173, truncated = 0
2.53.738.601 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.250 (> 0.100 thold), f_keep = 0.023
2.53.755.831 I slot launch_slot_: id  3 | task 755 | processing task, is_child = 0
3.14.358.177 I slot print_timing: id  3 | task 755 | prompt eval time =    1359.28 ms /    12 tokens (  113.27 ms per token,     8.83 tokens per second)
3.14.358.207 I slot print_timing: id  3 | task 755 |        eval time =   19240.26 ms /   100 tokens (  194.35 ms per token,     5.15 tokens per second)
3.14.358.877 I slot print_timing: id  3 | task 755 |       total time =   20599.54 ms /   112 tokens
3.14.358.881 I slot print_timing: id  3 | task 755 |    graphs reused =        847
3.14.362.840 I slot      release: id  3 | task 755 | stop processing: n_tokens = 115, truncated = 0
3.14.455.830 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
3.14.467.775 I slot launch_slot_: id  3 | task 856 | processing task, is_child = 0
3.14.468.563 W slot   operator(): id  3 | task 856 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
3.14.468.568 W slot   operator(): id  3 | task 856 | n_past was set to 15
3.33.365.578 I slot print_timing: id  3 | task 856 | prompt eval time =     147.17 ms /     1 tokens (  147.17 ms per token,     6.79 tokens per second)
3.33.365.617 I slot print_timing: id  3 | task 856 |        eval time =   18748.46 ms /   100 tokens (  189.38 ms per token,     5.28 tokens per second)
3.33.366.440 I slot print_timing: id  3 | task 856 |       total time =   18895.63 ms /   101 tokens
3.33.366.447 I slot print_timing: id  3 | task 856 |    graphs reused =        947
3.33.369.922 I slot      release: id  3 | task 856 | stop processing: n_tokens = 115, truncated = 0
3.33.479.411 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
3.33.489.864 I slot launch_slot_: id  3 | task 957 | processing task, is_child = 0
3.33.490.261 W slot   operator(): id  3 | task 957 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
3.33.490.270 W slot   operator(): id  3 | task 957 | n_past was set to 15
3.49.079.605 I slot print_timing: id  3 | task 957 | prompt eval time =     219.78 ms /     1 tokens (  219.78 ms per token,     4.55 tokens per second)
3.49.079.618 I slot print_timing: id  3 | task 957 |        eval time =   15368.76 ms /   100 tokens (  155.24 ms per token,     6.44 tokens per second)
3.49.079.622 I slot print_timing: id  3 | task 957 |       total time =   15588.54 ms /   101 tokens
3.49.079.624 I slot print_timing: id  3 | task 957 |    graphs reused =       1047
3.49.080.533 I slot      release: id  3 | task 957 | stop processing: n_tokens = 115, truncated = 0
3.49.120.399 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
3.49.121.101 I slot launch_slot_: id  3 | task 1058 | processing task, is_child = 0
3.49.121.145 W slot   operator(): id  3 | task 1058 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
3.49.121.180 W slot   operator(): id  3 | task 1058 | n_past was set to 15
4.05.022.526 I slot print_timing: id  3 | task 1058 | prompt eval time =     149.20 ms /     1 tokens (  149.20 ms per token,     6.70 tokens per second)
4.05.022.539 I slot print_timing: id  3 | task 1058 |        eval time =   15752.13 ms /   100 tokens (  159.11 ms per token,     6.28 tokens per second)
4.05.022.542 I slot print_timing: id  3 | task 1058 |       total time =   15901.33 ms /   101 tokens
4.05.022.544 I slot print_timing: id  3 | task 1058 |    graphs reused =       1147
4.05.022.599 I slot      release: id  3 | task 1058 | stop processing: n_tokens = 115, truncated = 0
4.05.048.367 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
4.05.049.178 I slot launch_slot_: id  3 | task 1159 | processing task, is_child = 0
4.05.049.241 W slot   operator(): id  3 | task 1159 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
4.05.049.243 W slot   operator(): id  3 | task 1159 | n_past was set to 15
4.19.271.538 I slot print_timing: id  3 | task 1159 | prompt eval time =     153.54 ms /     1 tokens (  153.54 ms per token,     6.51 tokens per second)
4.19.271.551 I slot print_timing: id  3 | task 1159 |        eval time =   14068.74 ms /   100 tokens (  142.11 ms per token,     7.04 tokens per second)
4.19.271.553 I slot print_timing: id  3 | task 1159 |       total time =   14222.28 ms /   101 tokens
4.19.271.555 I slot print_timing: id  3 | task 1159 |    graphs reused =       1247
4.19.271.597 I slot      release: id  3 | task 1159 | stop processing: n_tokens = 115, truncated = 0
4.19.321.609 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
4.19.321.992 I slot launch_slot_: id  3 | task 1260 | processing task, is_child = 0
4.19.322.039 W slot   operator(): id  3 | task 1260 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
4.19.322.041 W slot   operator(): id  3 | task 1260 | n_past was set to 15
4.35.463.312 I slot print_timing: id  3 | task 1260 | prompt eval time =     142.96 ms /     1 tokens (  142.96 ms per token,     6.99 tokens per second)
4.35.463.322 I slot print_timing: id  3 | task 1260 |        eval time =   15998.29 ms /   100 tokens (  161.60 ms per token,     6.19 tokens per second)
4.35.463.325 I slot print_timing: id  3 | task 1260 |       total time =   16141.25 ms /   101 tokens
4.35.463.327 I slot print_timing: id  3 | task 1260 |    graphs reused =       1347
4.35.463.387 I slot      release: id  3 | task 1260 | stop processing: n_tokens = 115, truncated = 0
4.35.482.993 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
4.35.483.354 I slot launch_slot_: id  3 | task 1361 | processing task, is_child = 0
4.35.483.392 W slot   operator(): id  3 | task 1361 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
4.35.483.393 W slot   operator(): id  3 | task 1361 | n_past was set to 15
4.55.907.336 I slot print_timing: id  3 | task 1361 | prompt eval time =     591.96 ms /     1 tokens (  591.96 ms per token,     1.69 tokens per second)
4.55.907.388 I slot print_timing: id  3 | task 1361 |        eval time =   19829.67 ms /   100 tokens (  200.30 ms per token,     4.99 tokens per second)
4.55.907.993 I slot print_timing: id  3 | task 1361 |       total time =   20421.63 ms /   101 tokens
4.55.907.999 I slot print_timing: id  3 | task 1361 |    graphs reused =       1447
4.55.912.123 I slot      release: id  3 | task 1361 | stop processing: n_tokens = 115, truncated = 0
4.55.993.113 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
4.55.995.875 I slot launch_slot_: id  3 | task 1462 | processing task, is_child = 0
4.55.996.632 W slot   operator(): id  3 | task 1462 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
4.55.996.638 W slot   operator(): id  3 | task 1462 | n_past was set to 15
5.11.903.857 I slot print_timing: id  3 | task 1462 | prompt eval time =     219.02 ms /     1 tokens (  219.02 ms per token,     4.57 tokens per second)
5.11.903.886 I slot print_timing: id  3 | task 1462 |        eval time =   15688.47 ms /   100 tokens (  158.47 ms per token,     6.31 tokens per second)
5.11.903.894 I slot print_timing: id  3 | task 1462 |       total time =   15907.49 ms /   101 tokens
5.11.903.904 I slot print_timing: id  3 | task 1462 |    graphs reused =       1547
5.11.904.203 I slot      release: id  3 | task 1462 | stop processing: n_tokens = 115, truncated = 0
5.11.924.919 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
5.11.925.396 I slot launch_slot_: id  3 | task 1563 | processing task, is_child = 0
5.11.925.443 W slot   operator(): id  3 | task 1563 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
5.11.925.444 W slot   operator(): id  3 | task 1563 | n_past was set to 15
5.29.975.710 I slot print_timing: id  3 | task 1563 | prompt eval time =     231.51 ms /     1 tokens (  231.51 ms per token,     4.32 tokens per second)
5.29.975.738 I slot print_timing: id  3 | task 1563 |        eval time =   17817.32 ms /   100 tokens (  179.97 ms per token,     5.56 tokens per second)
5.29.975.746 I slot print_timing: id  3 | task 1563 |       total time =   18048.83 ms /   101 tokens
5.29.975.750 I slot print_timing: id  3 | task 1563 |    graphs reused =       1647
5.29.977.423 I slot      release: id  3 | task 1563 | stop processing: n_tokens = 115, truncated = 0
5.30.024.847 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.139
5.30.025.821 I slot launch_slot_: id  3 | task 1664 | processing task, is_child = 0
5.30.025.896 W slot   operator(): id  3 | task 1664 | need to evaluate at least 1 token for each active slot (n_past = 16, task.n_tokens() = 16)
5.30.025.898 W slot   operator(): id  3 | task 1664 | n_past was set to 15
5.44.446.814 I slot print_timing: id  3 | task 1664 | prompt eval time =     221.35 ms /     1 tokens (  221.35 ms per token,     4.52 tokens per second)
5.44.446.827 I slot print_timing: id  3 | task 1664 |        eval time =   14199.55 ms /   100 tokens (  143.43 ms per token,     6.97 tokens per second)
5.44.446.830 I slot print_timing: id  3 | task 1664 |       total time =   14420.90 ms /   101 tokens
5.44.446.863 I slot print_timing: id  3 | task 1664 |    graphs reused =       1747
5.44.446.934 I slot      release: id  3 | task 1664 | stop processing: n_tokens = 115, truncated = 0
5.44.734.331 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.263 (> 0.100 thold), f_keep = 0.043
5.44.738.850 I slot launch_slot_: id  3 | task 1765 | processing task, is_child = 0
5.58.795.077 I slot print_timing: id  3 | task 1765 | prompt eval time =    1425.02 ms /    14 tokens (  101.79 ms per token,     9.82 tokens per second)
5.58.795.090 I slot print_timing: id  3 | task 1765 |        eval time =   12630.80 ms /    80 tokens (  159.88 ms per token,     6.25 tokens per second)
5.58.795.093 I slot print_timing: id  3 | task 1765 |       total time =   14055.82 ms /    94 tokens
5.58.795.096 I slot print_timing: id  3 | task 1765 |    graphs reused =       1825
5.58.795.164 I slot      release: id  3 | task 1765 | stop processing: n_tokens = 98, truncated = 0
5.58.815.996 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.194
5.58.828.020 I slot launch_slot_: id  3 | task 1846 | processing task, is_child = 0
5.58.828.465 W slot   operator(): id  3 | task 1846 | need to evaluate at least 1 token for each active slot (n_past = 19, task.n_tokens() = 19)
5.58.828.478 W slot   operator(): id  3 | task 1846 | n_past was set to 18
6.11.002.719 I slot print_timing: id  3 | task 1846 | prompt eval time =     176.78 ms /     1 tokens (  176.78 ms per token,     5.66 tokens per second)
6.11.002.729 I slot print_timing: id  3 | task 1846 |        eval time =   11997.82 ms /    80 tokens (  151.87 ms per token,     6.58 tokens per second)
6.11.002.732 I slot print_timing: id  3 | task 1846 |       total time =   12174.61 ms /    81 tokens
6.11.002.733 I slot print_timing: id  3 | task 1846 |    graphs reused =       1905
6.11.002.823 I slot      release: id  3 | task 1846 | stop processing: n_tokens = 98, truncated = 0
6.11.039.103 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.194
6.11.050.078 I slot launch_slot_: id  3 | task 1927 | processing task, is_child = 0
6.11.050.146 W slot   operator(): id  3 | task 1927 | need to evaluate at least 1 token for each active slot (n_past = 19, task.n_tokens() = 19)
6.11.050.147 W slot   operator(): id  3 | task 1927 | n_past was set to 18
6.23.403.747 I slot print_timing: id  3 | task 1927 | prompt eval time =     135.26 ms /     1 tokens (  135.26 ms per token,     7.39 tokens per second)
6.23.403.760 I slot print_timing: id  3 | task 1927 |        eval time =   12218.31 ms /    80 tokens (  154.66 ms per token,     6.47 tokens per second)
6.23.403.762 I slot print_timing: id  3 | task 1927 |       total time =   12353.56 ms /    81 tokens
6.23.403.764 I slot print_timing: id  3 | task 1927 |    graphs reused =       1985
6.23.403.819 I slot      release: id  3 | task 1927 | stop processing: n_tokens = 98, truncated = 0
6.23.445.802 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.194
6.23.457.667 I slot launch_slot_: id  3 | task 2008 | processing task, is_child = 0
6.23.458.441 W slot   operator(): id  3 | task 2008 | need to evaluate at least 1 token for each active slot (n_past = 19, task.n_tokens() = 19)
6.23.458.468 W slot   operator(): id  3 | task 2008 | n_past was set to 18
6.37.463.982 I slot print_timing: id  3 | task 2008 | prompt eval time =     150.23 ms /     1 tokens (  150.23 ms per token,     6.66 tokens per second)
6.37.464.009 I slot print_timing: id  3 | task 2008 |        eval time =   13852.97 ms /    80 tokens (  175.35 ms per token,     5.70 tokens per second)
6.37.464.640 I slot print_timing: id  3 | task 2008 |       total time =   14003.19 ms /    81 tokens
6.37.464.657 I slot print_timing: id  3 | task 2008 |    graphs reused =       2065
6.37.469.424 I slot      release: id  3 | task 2008 | stop processing: n_tokens = 98, truncated = 0
6.37.570.198 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.194
6.37.581.147 I slot launch_slot_: id  3 | task 2089 | processing task, is_child = 0
6.37.581.848 W slot   operator(): id  3 | task 2089 | need to evaluate at least 1 token for each active slot (n_past = 19, task.n_tokens() = 19)
6.37.581.852 W slot   operator(): id  3 | task 2089 | n_past was set to 18
6.50.992.628 I slot print_timing: id  3 | task 2089 | prompt eval time =     144.86 ms /     1 tokens (  144.86 ms per token,     6.90 tokens per second)
6.50.992.657 I slot print_timing: id  3 | task 2089 |        eval time =   13264.75 ms /    80 tokens (  167.91 ms per token,     5.96 tokens per second)
6.50.993.132 I slot print_timing: id  3 | task 2089 |       total time =   13409.61 ms /    81 tokens
6.50.993.136 I slot print_timing: id  3 | task 2089 |    graphs reused =       2145
6.50.996.874 I slot      release: id  3 | task 2089 | stop processing: n_tokens = 98, truncated = 0
6.51.230.294 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.176 (> 0.100 thold), f_keep = 0.031
6.51.265.745 I slot launch_slot_: id  3 | task 2170 | processing task, is_child = 0
7.11.237.390 I slot print_timing: id  3 | task 2170 | prompt eval time =    2139.08 ms /    14 tokens (  152.79 ms per token,     6.54 tokens per second)
7.11.237.439 I slot print_timing: id  3 | task 2170 |        eval time =   17829.69 ms /   100 tokens (  180.10 ms per token,     5.55 tokens per second)
7.11.238.142 I slot print_timing: id  3 | task 2170 |       total time =   19968.77 ms /   114 tokens
7.11.238.149 I slot print_timing: id  3 | task 2170 |    graphs reused =       2243
7.11.243.228 I slot      release: id  3 | task 2170 | stop processing: n_tokens = 116, truncated = 0
7.11.423.014 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.176 (> 0.100 thold), f_keep = 0.026
7.11.447.670 I slot launch_slot_: id  3 | task 2271 | processing task, is_child = 0
7.30.149.095 I slot print_timing: id  3 | task 2271 | prompt eval time =    1675.90 ms /    14 tokens (  119.71 ms per token,     8.35 tokens per second)
7.30.149.130 I slot print_timing: id  3 | task 2271 |        eval time =   17024.23 ms /   100 tokens (  171.96 ms per token,     5.82 tokens per second)
7.30.149.140 I slot print_timing: id  3 | task 2271 |       total time =   18700.12 ms /   114 tokens
7.30.149.144 I slot print_timing: id  3 | task 2271 |    graphs reused =       2341
7.30.150.814 I slot      release: id  3 | task 2271 | stop processing: n_tokens = 116, truncated = 0
7.30.193.654 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.147
7.30.202.388 I slot launch_slot_: id  3 | task 2372 | processing task, is_child = 0
7.30.202.858 W slot   operator(): id  3 | task 2372 | need to evaluate at least 1 token for each active slot (n_past = 17, task.n_tokens() = 17)
7.30.202.868 W slot   operator(): id  3 | task 2372 | n_past was set to 16
7.49.776.093 I slot print_timing: id  3 | task 2372 | prompt eval time =     144.05 ms /     1 tokens (  144.05 ms per token,     6.94 tokens per second)
7.49.776.121 I slot print_timing: id  3 | task 2372 |        eval time =   19427.10 ms /   100 tokens (  196.23 ms per token,     5.10 tokens per second)
7.49.776.791 I slot print_timing: id  3 | task 2372 |       total time =   19571.15 ms /   101 tokens
7.49.776.796 I slot print_timing: id  3 | task 2372 |    graphs reused =       2441
7.49.781.008 I slot      release: id  3 | task 2372 | stop processing: n_tokens = 116, truncated = 0
7.49.922.114 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.147
7.49.932.568 I slot launch_slot_: id  3 | task 2473 | processing task, is_child = 0
7.49.933.173 W slot   operator(): id  3 | task 2473 | need to evaluate at least 1 token for each active slot (n_past = 17, task.n_tokens() = 17)
7.49.933.178 W slot   operator(): id  3 | task 2473 | n_past was set to 16
8.09.114.346 I slot print_timing: id  3 | task 2473 | prompt eval time =     154.32 ms /     1 tokens (  154.32 ms per token,     6.48 tokens per second)
8.09.114.368 I slot print_timing: id  3 | task 2473 |        eval time =   19024.27 ms /   100 tokens (  192.16 ms per token,     5.20 tokens per second)
8.09.115.030 I slot print_timing: id  3 | task 2473 |       total time =   19178.60 ms /   101 tokens
8.09.115.043 I slot print_timing: id  3 | task 2473 |    graphs reused =       2541
8.09.119.239 I slot      release: id  3 | task 2473 | stop processing: n_tokens = 116, truncated = 0
8.09.262.495 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.147
8.09.273.502 I slot launch_slot_: id  3 | task 2574 | processing task, is_child = 0
8.09.274.252 W slot   operator(): id  3 | task 2574 | need to evaluate at least 1 token for each active slot (n_past = 17, task.n_tokens() = 17)
8.09.274.257 W slot   operator(): id  3 | task 2574 | n_past was set to 16
8.28.556.143 I slot print_timing: id  3 | task 2574 | prompt eval time =     139.50 ms /     1 tokens (  139.50 ms per token,     7.17 tokens per second)
8.28.556.174 I slot print_timing: id  3 | task 2574 |        eval time =   19142.60 ms /   100 tokens (  193.36 ms per token,     5.17 tokens per second)
8.28.556.193 I slot print_timing: id  3 | task 2574 |       total time =   19282.10 ms /   101 tokens
8.28.556.197 I slot print_timing: id  3 | task 2574 |    graphs reused =       2641
8.28.556.613 I slot      release: id  3 | task 2574 | stop processing: n_tokens = 116, truncated = 0
8.28.818.549 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.167 (> 0.100 thold), f_keep = 0.026
8.28.827.587 I slot launch_slot_: id  3 | task 2675 | processing task, is_child = 0
8.48.582.037 I slot print_timing: id  3 | task 2675 | n_gen =    100, tg =   5.52 t/s, tg_3s =   5.58 t/s
8.51.621.073 I slot print_timing: id  3 | task 2675 | n_gen =    120, tg =   5.68 t/s, tg_3s =   6.57 t/s
8.54.721.286 I slot print_timing: id  3 | task 2675 | n_gen =    139, tg =   5.73 t/s, tg_3s =   6.13 t/s
8.57.866.755 I slot print_timing: id  3 | task 2675 | n_gen =    158, tg =   5.77 t/s, tg_3s =   6.04 t/s
9.00.872.432 I slot print_timing: id  3 | task 2675 | n_gen =    177, tg =   5.82 t/s, tg_3s =   6.32 t/s
9.04.029.690 I slot print_timing: id  3 | task 2675 | n_gen =    196, tg =   5.84 t/s, tg_3s =   6.02 t/s
9.04.642.468 I slot print_timing: id  3 | task 2675 | prompt eval time =    1827.76 ms /    15 tokens (  121.85 ms per token,     8.21 tokens per second)
9.04.642.483 I slot print_timing: id  3 | task 2675 |        eval time =   33985.88 ms /   200 tokens (  170.78 ms per token,     5.86 tokens per second)
9.04.642.945 I slot print_timing: id  3 | task 2675 |       total time =   35813.65 ms /   215 tokens
9.04.642.961 I slot print_timing: id  3 | task 2675 |    graphs reused =       2839
9.04.647.581 I slot      release: id  3 | task 2675 | stop processing: n_tokens = 217, truncated = 0
9.04.794.126 I slot get_availabl: id  2 | task -1 | selected slot by LRU, t_last = -1
9.04.796.461 I slot launch_slot_: id  2 | task 2876 | processing task, is_child = 0
9.25.940.514 I slot print_timing: id  2 | task 2876 | n_gen =    100, tg =   5.60 t/s, tg_3s =   5.65 t/s
9.29.100.708 I slot print_timing: id  2 | task 2876 | n_gen =    114, tg =   5.42 t/s, tg_3s =   4.43 t/s
9.32.222.965 I slot print_timing: id  2 | task 2876 | n_gen =    129, tg =   5.34 t/s, tg_3s =   4.81 t/s
9.35.317.043 I slot print_timing: id  2 | task 2876 | n_gen =    146, tg =   5.36 t/s, tg_3s =   5.49 t/s
9.38.404.697 I slot print_timing: id  2 | task 2876 | n_gen =    162, tg =   5.34 t/s, tg_3s =   5.18 t/s
9.41.448.004 I slot print_timing: id  2 | task 2876 | n_gen =    178, tg =   5.33 t/s, tg_3s =   5.26 t/s
9.44.524.126 I slot print_timing: id  2 | task 2876 | n_gen =    192, tg =   5.27 t/s, tg_3s =   4.55 t/s
9.46.085.849 I slot print_timing: id  2 | task 2876 | prompt eval time =    3419.55 ms /    33 tokens (  103.62 ms per token,     9.65 tokens per second)
9.46.085.890 I slot print_timing: id  2 | task 2876 |        eval time =   37836.61 ms /   200 tokens (  190.13 ms per token,     5.26 tokens per second)
9.46.086.277 I slot print_timing: id  2 | task 2876 |       total time =   41256.16 ms /   233 tokens
9.46.086.580 I slot print_timing: id  2 | task 2876 |    graphs reused =       3037
9.46.092.472 I slot      release: id  2 | task 2876 | stop processing: n_tokens = 232, truncated = 0
9.46.345.008 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.143 (> 0.100 thold), f_keep = 0.013
9.46.371.098 I slot launch_slot_: id  2 | task 3077 | processing task, is_child = 0
10.07.488.544 I slot print_timing: id  2 | task 3077 | n_gen =    100, tg =   5.13 t/s, tg_3s =   5.18 t/s
10.10.602.033 I slot print_timing: id  2 | task 3077 | n_gen =    115, tg =   5.09 t/s, tg_3s =   4.81 t/s
10.13.714.090 I slot print_timing: id  2 | task 3077 | n_gen =    135, tg =   5.25 t/s, tg_3s =   6.43 t/s
10.16.730.889 I slot print_timing: id  2 | task 3077 | n_gen =    153, tg =   5.33 t/s, tg_3s =   5.97 t/s
10.19.799.986 I slot print_timing: id  2 | task 3077 | n_gen =    173, tg =   5.44 t/s, tg_3s =   6.52 t/s
10.22.972.072 I slot print_timing: id  2 | task 3077 | n_gen =    189, tg =   5.41 t/s, tg_3s =   5.05 t/s
10.24.756.937 I slot print_timing: id  2 | task 3077 | prompt eval time =    1819.18 ms /    18 tokens (  101.07 ms per token,     9.89 tokens per second)
10.24.756.949 I slot print_timing: id  2 | task 3077 |        eval time =   36565.63 ms /   200 tokens (  183.75 ms per token,     5.44 tokens per second)
10.24.757.414 I slot print_timing: id  2 | task 3077 |       total time =   38384.81 ms /   218 tokens
10.24.757.426 I slot print_timing: id  2 | task 3077 |    graphs reused =       3235
10.24.761.705 I slot      release: id  2 | task 3077 | stop processing: n_tokens = 220, truncated = 0
```