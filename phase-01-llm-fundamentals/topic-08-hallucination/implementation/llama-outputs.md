```
Microsoft Windows [Version 10.0.26300.9711]
(c) Microsoft Corporation. All rights reserved.

C:\Users\Hp>llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M -ngl 0 -c 4096 --host 127.0.0.1 --port 8080
0.00.001.019 I srv  llama_server: initializing ...
0.00.716.915 I cmn  common_param: common_params_print_info: verbosity = 3 (adjust with the `-lv N` CLI arg)
0.00.717.296 W srv  llama_server: security: no API key is set and CORS allows all origins (see https://github.com/ggml-org/llama.cpp/pull/25655)
0.00.722.935 I srv    load_model: loading model 'Qwen/Qwen3-4B-GGUF:Q4_K_M'
0.01.387.964 W load: control-looking token: 128247 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.05.611.894 I cmn          init: llama threadpool init, n_threads = 4
0.06.948.281 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
0.07.032.980 I srv  llama_server: model loaded
0.07.033.242 I srv  llama_server: listening on http://127.0.0.1:8080
0.07.033.247 W srv  llama_server: notice: server default port will be changed to :9931 in a future release (ref: https://github.com/ggml-org/llama.cpp/pull/26508)
0.41.804.626 I slot get_availabl: id  3 | task -1 | selected slot by LRU, t_last = -1
0.41.814.720 I slot launch_slot_: id  3 | task 0 | processing task, is_child = 0
1.02.183.828 I slot print_timing: id  3 | task 0 | n_gen =    100, tg =   5.67 t/s, tg_3s =   5.73 t/s
1.05.261.084 I slot print_timing: id  3 | task 0 | n_gen =    120, tg =   5.80 t/s, tg_3s =   6.49 t/s
1.08.313.469 I slot print_timing: id  3 | task 0 | n_gen =    138, tg =   5.81 t/s, tg_3s =   5.90 t/s
1.11.477.082 I slot print_timing: id  3 | task 0 | n_gen =    153, tg =   5.68 t/s, tg_3s =   4.74 t/s
1.14.640.078 I slot print_timing: id  3 | task 0 | n_gen =    167, tg =   5.55 t/s, tg_3s =   4.43 t/s
1.17.780.015 I slot print_timing: id  3 | task 0 | n_gen =    185, tg =   5.57 t/s, tg_3s =   5.73 t/s
1.18.697.046 I slot print_timing: id  3 | task 0 | prompt eval time =    2909.61 ms /    32 tokens (   90.93 ms per token,    11.00 tokens per second)
1.18.697.058 I slot print_timing: id  3 | task 0 |        eval time =   33968.45 ms /   191 tokens (  178.78 ms per token,     5.59 tokens per second)
1.18.697.543 I slot print_timing: id  3 | task 0 |       total time =   36878.06 ms /   223 tokens
1.18.697.936 I slot print_timing: id  3 | task 0 |    graphs reused =        190
1.18.707.512 I slot      release: id  3 | task 0 | stop processing: n_tokens = 222, truncated = 0
1.19.011.214 I slot get_availabl: id  2 | task -1 | selected slot by LRU, t_last = -1
1.19.013.574 I slot launch_slot_: id  2 | task 192 | processing task, is_child = 0
1.40.328.220 I slot print_timing: id  2 | task 192 | n_gen =    100, tg =   5.49 t/s, tg_3s =   5.54 t/s
1.43.367.482 I slot print_timing: id  2 | task 192 | n_gen =    118, tg =   5.55 t/s, tg_3s =   5.92 t/s
1.46.482.897 I slot print_timing: id  2 | task 192 | n_gen =    136, tg =   5.58 t/s, tg_3s =   5.78 t/s
1.48.071.088 I slot print_timing: id  2 | task 192 | prompt eval time =    3263.27 ms /   198 tokens (   16.48 ms per token,    60.68 tokens per second)
1.48.071.103 I slot print_timing: id  2 | task 192 |        eval time =   25776.25 ms /   144 tokens (  180.25 ms per token,     5.55 tokens per second)
1.48.071.551 I slot print_timing: id  2 | task 192 |       total time =   29039.53 ms /   342 tokens
1.48.071.900 I slot print_timing: id  2 | task 192 |    graphs reused =        331
1.48.088.243 I slot      release: id  2 | task 192 | stop processing: n_tokens = 341, truncated = 0
1.48.553.271 I slot get_availabl: id  1 | task -1 | selected slot by LRU, t_last = -1
1.48.555.598 I slot launch_slot_: id  1 | task 337 | processing task, is_child = 0
1.53.402.772 I slot print_timing: id  1 | task 337 | prompt eval time =    1785.87 ms /    68 tokens (   26.26 ms per token,    38.08 tokens per second)
1.53.402.798 I slot print_timing: id  1 | task 337 |        eval time =    2995.11 ms /    10 tokens (  332.79 ms per token,     3.00 tokens per second)
1.53.403.091 I slot print_timing: id  1 | task 337 |       total time =    4780.99 ms /    78 tokens
1.53.403.100 I slot print_timing: id  1 | task 337 |    graphs reused =        339
1.53.411.291 I slot      release: id  1 | task 337 | stop processing: n_tokens = 77, truncated = 0
1.53.568.374 I slot get_availabl: id  1 | task -1 | selected slot by LCP similarity, f_sim_best = 0.714 (> 0.100 thold), f_keep = 0.519
1.53.569.258 I slot launch_slot_: id  1 | task 348 | processing task, is_child = 0
1.59.356.541 I slot print_timing: id  1 | task 348 | prompt eval time =    1566.28 ms /    16 tokens (   97.89 ms per token,    10.22 tokens per second)
1.59.356.552 I slot print_timing: id  1 | task 348 |        eval time =    4220.66 ms /    25 tokens (  175.86 ms per token,     5.69 tokens per second)
1.59.356.554 I slot print_timing: id  1 | task 348 |       total time =    5786.94 ms /    41 tokens
1.59.356.556 I slot print_timing: id  1 | task 348 |    graphs reused =        362
1.59.356.650 I slot      release: id  1 | task 348 | stop processing: n_tokens = 80, truncated = 0
1.59.479.077 I slot get_availabl: id  0 | task -1 | selected slot by LRU, t_last = -1
1.59.479.728 I slot launch_slot_: id  0 | task 374 | processing task, is_child = 0
2.18.188.203 I slot print_timing: id  0 | task 374 | n_gen =    100, tg =   5.70 t/s, tg_3s =   5.76 t/s
2.21.320.266 I slot print_timing: id  0 | task 374 | n_gen =    119, tg =   5.76 t/s, tg_3s =   6.06 t/s
2.24.452.834 I slot print_timing: id  0 | task 374 | n_gen =    136, tg =   5.71 t/s, tg_3s =   5.43 t/s
2.27.671.101 I slot print_timing: id  0 | task 374 | n_gen =    149, tg =   5.51 t/s, tg_3s =   4.04 t/s
2.28.345.368 I slot print_timing: id  0 | task 374 | prompt eval time =    1334.70 ms /    32 tokens (   41.71 ms per token,    23.98 tokens per second)
2.28.345.386 I slot print_timing: id  0 | task 374 |        eval time =   27519.85 ms /   150 tokens (  184.70 ms per token,     5.41 tokens per second)
2.28.345.924 I slot print_timing: id  0 | task 374 |       total time =   28854.56 ms /   182 tokens
2.28.346.764 I slot print_timing: id  0 | task 374 |    graphs reused =        510
2.28.352.596 I slot      release: id  0 | task 374 | stop processing: n_tokens = 181, truncated = 0
2.28.965.706 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.177
2.29.013.332 I slot launch_slot_: id  0 | task 525 | processing task, is_child = 0
2.29.014.823 W slot   operator(): id  0 | task 525 | need to evaluate at least 1 token for each active slot (n_past = 32, task.n_tokens() = 32)
2.29.014.834 W slot   operator(): id  0 | task 525 | n_past was set to 31
2.47.937.782 I slot print_timing: id  0 | task 525 | n_gen =    100, tg =   5.76 t/s, tg_3s =   5.81 t/s
2.50.985.541 I slot print_timing: id  0 | task 525 | n_gen =    114, tg =   5.58 t/s, tg_3s =   4.59 t/s
2.53.997.991 I slot print_timing: id  0 | task 525 | n_gen =    126, tg =   5.37 t/s, tg_3s =   3.99 t/s
2.56.997.583 I slot print_timing: id  0 | task 525 | n_gen =    140, tg =   5.29 t/s, tg_3s =   4.66 t/s
2.58.542.813 I slot print_timing: id  0 | task 525 | prompt eval time =    1719.23 ms /     1 tokens ( 1719.23 ms per token,     0.58 tokens per second)
2.58.542.838 I slot print_timing: id  0 | task 525 |        eval time =   27807.62 ms /   150 tokens (  186.63 ms per token,     5.36 tokens per second)
2.58.543.211 I slot print_timing: id  0 | task 525 |       total time =   29526.85 ms /   151 tokens
2.58.543.597 I slot print_timing: id  0 | task 525 |    graphs reused =        660
2.58.550.898 I slot      release: id  0 | task 525 | stop processing: n_tokens = 181, truncated = 0
2.58.682.567 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.177
2.58.700.250 I slot launch_slot_: id  0 | task 676 | processing task, is_child = 0
2.58.700.857 W slot   operator(): id  0 | task 676 | need to evaluate at least 1 token for each active slot (n_past = 32, task.n_tokens() = 32)
2.58.700.860 W slot   operator(): id  0 | task 676 | n_past was set to 31
3.16.905.694 I slot print_timing: id  0 | task 676 | n_gen =    100, tg =   5.48 t/s, tg_3s =   5.54 t/s
3.20.033.855 I slot print_timing: id  0 | task 676 | n_gen =    121, tg =   5.66 t/s, tg_3s =   6.71 t/s
3.23.188.376 I slot print_timing: id  0 | task 676 | n_gen =    139, tg =   5.67 t/s, tg_3s =   5.71 t/s
3.25.418.443 I slot print_timing: id  0 | task 676 | prompt eval time =     139.69 ms /     1 tokens (  139.69 ms per token,     7.16 tokens per second)
3.25.418.457 I slot print_timing: id  0 | task 676 |        eval time =   26577.27 ms /   150 tokens (  178.37 ms per token,     5.61 tokens per second)
3.25.418.463 I slot print_timing: id  0 | task 676 |       total time =   26716.95 ms /   151 tokens
3.25.418.900 I slot print_timing: id  0 | task 676 |    graphs reused =        810
3.25.419.185 I slot      release: id  0 | task 676 | stop processing: n_tokens = 181, truncated = 0
3.25.458.761 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.177
3.25.477.685 I slot launch_slot_: id  0 | task 827 | processing task, is_child = 0
3.25.477.751 W slot   operator(): id  0 | task 827 | need to evaluate at least 1 token for each active slot (n_past = 32, task.n_tokens() = 32)
3.25.477.752 W slot   operator(): id  0 | task 827 | n_past was set to 31
3.42.372.424 I slot print_timing: id  0 | task 827 | n_gen =    100, tg =   5.93 t/s, tg_3s =   5.99 t/s
3.45.388.202 I slot print_timing: id  0 | task 827 | n_gen =    118, tg =   5.93 t/s, tg_3s =   5.97 t/s
3.48.492.312 I slot print_timing: id  0 | task 827 | n_gen =    134, tg =   5.83 t/s, tg_3s =   5.15 t/s
3.51.130.385 I slot print_timing: id  0 | task 827 | prompt eval time =     187.49 ms /     1 tokens (  187.49 ms per token,     5.33 tokens per second)
3.51.130.395 I slot print_timing: id  0 | task 827 |        eval time =   25464.31 ms /   150 tokens (  170.90 ms per token,     5.85 tokens per second)
3.51.130.398 I slot print_timing: id  0 | task 827 |       total time =   25651.79 ms /   151 tokens
3.51.130.399 I slot print_timing: id  0 | task 827 |    graphs reused =        960
3.51.130.460 I slot      release: id  0 | task 827 | stop processing: n_tokens = 181, truncated = 0
3.51.155.645 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.177
3.51.168.607 I slot launch_slot_: id  0 | task 978 | processing task, is_child = 0
3.51.168.661 W slot   operator(): id  0 | task 978 | need to evaluate at least 1 token for each active slot (n_past = 32, task.n_tokens() = 32)
3.51.168.662 W slot   operator(): id  0 | task 978 | n_past was set to 31
4.07.063.402 I slot print_timing: id  0 | task 978 | n_gen =    100, tg =   6.29 t/s, tg_3s =   6.36 t/s
4.10.189.317 I slot print_timing: id  0 | task 978 | n_gen =    120, tg =   6.31 t/s, tg_3s =   6.40 t/s
4.13.213.693 I slot print_timing: id  0 | task 978 | n_gen =    139, tg =   6.31 t/s, tg_3s =   6.28 t/s
4.15.184.938 I slot print_timing: id  0 | task 978 | prompt eval time =     161.72 ms /     1 tokens (  161.72 ms per token,     6.18 tokens per second)
4.15.184.952 I slot print_timing: id  0 | task 978 |        eval time =   23853.83 ms /   150 tokens (  160.09 ms per token,     6.25 tokens per second)
4.15.184.954 I slot print_timing: id  0 | task 978 |       total time =   24015.55 ms /   151 tokens
4.15.184.957 I slot print_timing: id  0 | task 978 |    graphs reused =       1110
4.15.185.026 I slot      release: id  0 | task 978 | stop processing: n_tokens = 181, truncated = 0
4.15.666.698 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.177
4.15.732.499 I slot launch_slot_: id  0 | task 1129 | processing task, is_child = 0
4.15.734.792 W slot   operator(): id  0 | task 1129 | need to evaluate at least 1 token for each active slot (n_past = 32, task.n_tokens() = 32)
4.15.734.801 W slot   operator(): id  0 | task 1129 | n_past was set to 31
4.34.417.503 I slot print_timing: id  0 | task 1129 | n_gen =    100, tg =   5.40 t/s, tg_3s =   5.45 t/s
4.37.490.152 I slot print_timing: id  0 | task 1129 | n_gen =    120, tg =   5.56 t/s, tg_3s =   6.50 t/s
4.40.542.964 I slot print_timing: id  0 | task 1129 | n_gen =    140, tg =   5.68 t/s, tg_3s =   6.55 t/s
4.42.109.978 I slot print_timing: id  0 | task 1129 | prompt eval time =     341.91 ms /     1 tokens (  341.91 ms per token,     2.92 tokens per second)
4.42.109.989 I slot print_timing: id  0 | task 1129 |        eval time =   26033.20 ms /   150 tokens (  174.72 ms per token,     5.72 tokens per second)
4.42.110.499 I slot print_timing: id  0 | task 1129 |       total time =   26375.11 ms /   151 tokens
4.42.110.508 I slot print_timing: id  0 | task 1129 |    graphs reused =       1260
4.42.111.631 I slot      release: id  0 | task 1129 | stop processing: n_tokens = 181, truncated = 0
4.42.166.936 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.177
4.42.179.313 I slot launch_slot_: id  0 | task 1280 | processing task, is_child = 0
4.42.179.358 W slot   operator(): id  0 | task 1280 | need to evaluate at least 1 token for each active slot (n_past = 32, task.n_tokens() = 32)
4.42.179.359 W slot   operator(): id  0 | task 1280 | n_past was set to 31
4.58.291.952 I slot print_timing: id  0 | task 1280 | n_gen =    100, tg =   6.20 t/s, tg_3s =   6.26 t/s
5.01.335.422 I slot print_timing: id  0 | task 1280 | n_gen =    115, tg =   6.00 t/s, tg_3s =   4.93 t/s
5.04.401.149 I slot print_timing: id  0 | task 1280 | n_gen =    132, tg =   5.93 t/s, tg_3s =   5.55 t/s
5.07.263.376 I slot print_timing: id  0 | task 1280 | prompt eval time =     146.28 ms /     1 tokens (  146.28 ms per token,     6.84 tokens per second)
5.07.263.390 I slot print_timing: id  0 | task 1280 |        eval time =   24937.14 ms /   150 tokens (  167.36 ms per token,     5.98 tokens per second)
5.07.263.950 I slot print_timing: id  0 | task 1280 |       total time =   25083.42 ms /   151 tokens
5.07.263.960 I slot print_timing: id  0 | task 1280 |    graphs reused =       1410
5.07.264.031 I slot      release: id  0 | task 1280 | stop processing: n_tokens = 181, truncated = 0
5.07.302.995 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.177
5.07.303.441 I slot launch_slot_: id  0 | task 1431 | processing task, is_child = 0
5.07.303.485 W slot   operator(): id  0 | task 1431 | need to evaluate at least 1 token for each active slot (n_past = 32, task.n_tokens() = 32)
5.07.303.486 W slot   operator(): id  0 | task 1431 | n_past was set to 31
5.22.452.147 I slot print_timing: id  0 | task 1431 | n_gen =    100, tg =   6.60 t/s, tg_3s =   6.67 t/s
5.25.454.805 I slot print_timing: id  0 | task 1431 | n_gen =    120, tg =   6.61 t/s, tg_3s =   6.66 t/s
5.28.481.746 I slot print_timing: id  0 | task 1431 | n_gen =    140, tg =   6.61 t/s, tg_3s =   6.61 t/s
5.29.980.100 I slot print_timing: id  0 | task 1431 | prompt eval time =     144.62 ms /     1 tokens (  144.62 ms per token,     6.91 tokens per second)
5.29.980.114 I slot print_timing: id  0 | task 1431 |        eval time =   22531.46 ms /   150 tokens (  151.22 ms per token,     6.61 tokens per second)
5.29.980.116 I slot print_timing: id  0 | task 1431 |       total time =   22676.07 ms /   151 tokens
5.29.980.118 I slot print_timing: id  0 | task 1431 |    graphs reused =       1560
5.29.980.169 I slot      release: id  0 | task 1431 | stop processing: n_tokens = 181, truncated = 0
```