```cmd
C:\Users\Hp>llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M -ngl 0 -c 4096 --host 127.0.0.1 --port 8080
0.00.001.065 I srv  llama_server: initializing ...
0.01.236.223 I cmn  common_param: common_params_print_info: verbosity = 3 (adjust with the `-lv N` CLI arg)
0.01.254.555 W srv  llama_server: security: no API key is set and CORS allows all origins (see https://github.com/ggml-org/llama.cpp/pull/25655)
0.01.280.774 I srv    load_model: loading model 'Qwen/Qwen3-4B-GGUF:Q4_K_M'
0.02.090.079 W load: control-looking token: 128247 '</s>' was not control-type; this is probably a bug in the model. its type will be overridden
0.07.825.291 I cmn          init: llama threadpool init, n_threads = 4
0.09.286.977 I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
0.09.350.380 I srv  llama_server: model loaded
0.09.350.671 I srv  llama_server: listening on http://127.0.0.1:8080
0.09.350.677 W srv  llama_server: notice: server default port will be changed to :9931 in a future release (ref: https://github.com/ggml-org/llama.cpp/pull/26508)
0.14.790.548 I slot get_availabl: id  3 | task -1 | selected slot by LRU, t_last = -1
0.14.795.393 I slot launch_slot_: id  3 | task 0 | processing task, is_child = 0
0.26.524.536 I slot print_timing: id  3 | task 0 | prompt eval time =     962.41 ms /    63 tokens (   15.28 ms per token,    65.46 tokens per second)
0.26.524.555 I slot print_timing: id  3 | task 0 |        eval time =   10765.26 ms /    64 tokens (  170.88 ms per token,     5.85 tokens per second)
0.26.524.922 I slot print_timing: id  3 | task 0 |       total time =   11727.67 ms /   127 tokens
0.26.524.924 I slot print_timing: id  3 | task 0 |    graphs reused =         63
0.26.530.173 I slot      release: id  3 | task 0 | stop processing: n_tokens = 126, truncated = 0
0.26.698.947 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.500
0.26.699.301 I slot launch_slot_: id  3 | task 65 | processing task, is_child = 0
0.26.699.874 W slot   operator(): id  3 | task 65 | need to evaluate at least 1 token for each active slot (n_past = 63, task.n_tokens() = 63)
0.26.699.883 W slot   operator(): id  3 | task 65 | n_past was set to 62
0.40.987.781 I slot print_timing: id  3 | task 65 | prompt eval time =     179.32 ms /     1 tokens (  179.32 ms per token,     5.58 tokens per second)
0.40.987.794 I slot print_timing: id  3 | task 65 |        eval time =   14108.44 ms /    64 tokens (  223.94 ms per token,     4.47 tokens per second)
0.40.987.800 I slot print_timing: id  3 | task 65 |       total time =   14287.76 ms /    65 tokens
0.40.987.807 I slot print_timing: id  3 | task 65 |    graphs reused =        127
0.40.990.134 I slot      release: id  3 | task 65 | stop processing: n_tokens = 126, truncated = 0
0.41.126.895 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.250 (> 0.100 thold), f_keep = 0.079
0.41.141.793 I slot launch_slot_: id  3 | task 130 | processing task, is_child = 0
0.54.282.203 I slot print_timing: id  3 | task 130 | prompt eval time =    3442.07 ms /    30 tokens (  114.74 ms per token,     8.72 tokens per second)
0.54.282.214 I slot print_timing: id  3 | task 130 |        eval time =    9697.86 ms /    55 tokens (  179.59 ms per token,     5.57 tokens per second)
0.54.282.217 I slot print_timing: id  3 | task 130 |       total time =   13139.93 ms /    85 tokens
0.54.282.219 I slot print_timing: id  3 | task 130 |    graphs reused =        180
0.54.284.156 I slot      release: id  3 | task 130 | stop processing: n_tokens = 94, truncated = 0
0.54.318.402 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.270 (> 0.100 thold), f_keep = 0.106
0.54.326.495 I slot launch_slot_: id  3 | task 186 | processing task, is_child = 0
1.02.966.052 I slot print_timing: id  3 | task 186 | prompt eval time =    2475.94 ms /    27 tokens (   91.70 ms per token,    10.90 tokens per second)
1.02.966.065 I slot print_timing: id  3 | task 186 |        eval time =    6163.54 ms /    36 tokens (  176.10 ms per token,     5.68 tokens per second)
1.02.966.068 I slot print_timing: id  3 | task 186 |       total time =    8639.48 ms /    63 tokens
1.02.966.070 I slot print_timing: id  3 | task 186 |    graphs reused =        214
1.02.966.900 I slot      release: id  3 | task 186 | stop processing: n_tokens = 72, truncated = 0
1.03.027.856 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.179 (> 0.100 thold), f_keep = 0.139
1.03.034.454 I slot launch_slot_: id  3 | task 223 | processing task, is_child = 0
1.12.537.373 I slot print_timing: id  3 | task 223 | prompt eval time =    1100.22 ms /    46 tokens (   23.92 ms per token,    41.81 tokens per second)
1.12.537.382 I slot print_timing: id  3 | task 223 |        eval time =    8402.38 ms /    58 tokens (  147.41 ms per token,     6.78 tokens per second)
1.12.538.402 I slot print_timing: id  3 | task 223 |       total time =    9502.60 ms /   104 tokens
1.12.538.421 I slot print_timing: id  3 | task 223 |    graphs reused =        270
1.12.543.606 I slot      release: id  3 | task 223 | stop processing: n_tokens = 113, truncated = 0
1.12.623.293 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.169 (> 0.100 thold), f_keep = 0.088
1.12.631.289 I slot launch_slot_: id  3 | task 282 | processing task, is_child = 0
1.22.262.839 I slot print_timing: id  3 | task 282 | prompt eval time =     937.17 ms /    49 tokens (   19.13 ms per token,    52.29 tokens per second)
1.22.262.848 I slot print_timing: id  3 | task 282 |        eval time =    8694.02 ms /    64 tokens (  138.00 ms per token,     7.25 tokens per second)
1.22.262.850 I slot print_timing: id  3 | task 282 |       total time =    9631.18 ms /   113 tokens
1.22.262.852 I slot print_timing: id  3 | task 282 |    graphs reused =        332
1.22.264.212 I slot      release: id  3 | task 282 | stop processing: n_tokens = 122, truncated = 0
1.22.312.196 I slot get_availabl: id  3 | task -1 | selected slot by LCP similarity, f_sim_best = 0.177 (> 0.100 thold), f_keep = 0.090
1.22.320.257 I slot launch_slot_: id  3 | task 347 | processing task, is_child = 0
1.23.385.186 I slot print_timing: id  3 | task 347 | prompt eval time =     913.30 ms /    51 tokens (   17.91 ms per token,    55.84 tokens per second)
1.23.385.196 I slot print_timing: id  3 | task 347 |        eval time =     151.57 ms /     2 tokens (  151.57 ms per token,     6.60 tokens per second)
1.23.385.198 I slot print_timing: id  3 | task 347 |       total time =    1064.87 ms /    53 tokens
1.23.385.199 I slot print_timing: id  3 | task 347 |    graphs reused =        332
1.23.386.394 I slot      release: id  3 | task 347 | stop processing: n_tokens = 63, truncated = 0
1.23.660.365 I slot get_availabl: id  2 | task -1 | selected slot by LRU, t_last = -1
1.23.660.767 I slot launch_slot_: id  2 | task 350 | processing task, is_child = 0
1.33.973.633 I slot print_timing: id  2 | task 350 | prompt eval time =    2221.43 ms /   183 tokens (   12.14 ms per token,    82.38 tokens per second)
1.33.973.644 I slot print_timing: id  2 | task 350 |        eval time =    8087.93 ms /    52 tokens (  158.59 ms per token,     6.31 tokens per second)
1.33.973.646 I slot print_timing: id  2 | task 350 |       total time =   10309.36 ms /   235 tokens
1.33.973.647 I slot print_timing: id  2 | task 350 |    graphs reused =        382
1.33.985.410 I slot      release: id  2 | task 350 | stop processing: n_tokens = 234, truncated = 0
1.34.025.293 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.812 (> 0.100 thold), f_keep = 0.556
1.34.025.665 I slot launch_slot_: id  2 | task 403 | processing task, is_child = 0
1.37.983.924 I slot print_timing: id  2 | task 403 | prompt eval time =    2680.57 ms /    30 tokens (   89.35 ms per token,    11.19 tokens per second)
1.37.983.955 I slot print_timing: id  2 | task 403 |        eval time =    1277.13 ms /     9 tokens (  159.64 ms per token,     6.26 tokens per second)
1.37.983.962 I slot print_timing: id  2 | task 403 |       total time =    3957.70 ms /    39 tokens
1.37.983.964 I slot print_timing: id  2 | task 403 |    graphs reused =        389
1.37.984.892 I slot      release: id  2 | task 403 | stop processing: n_tokens = 168, truncated = 0
1.38.011.610 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.828 (> 0.100 thold), f_keep = 0.774
1.38.011.952 I slot launch_slot_: id  2 | task 413 | processing task, is_child = 0
1.46.281.034 I slot print_timing: id  2 | task 413 | prompt eval time =    2984.79 ms /    27 tokens (  110.55 ms per token,     9.05 tokens per second)
1.46.281.046 I slot print_timing: id  2 | task 413 |        eval time =    5284.21 ms /    26 tokens (  211.37 ms per token,     4.73 tokens per second)
1.46.281.056 I slot print_timing: id  2 | task 413 |       total time =    8269.00 ms /    53 tokens
1.46.281.058 I slot print_timing: id  2 | task 413 |    graphs reused =        413
1.46.282.299 I slot      release: id  2 | task 413 | stop processing: n_tokens = 182, truncated = 0
1.46.327.289 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.739 (> 0.100 thold), f_keep = 0.714
1.46.327.726 I slot launch_slot_: id  2 | task 440 | processing task, is_child = 0
1.54.462.954 I slot print_timing: id  2 | task 440 | prompt eval time =    1030.64 ms /    46 tokens (   22.41 ms per token,    44.63 tokens per second)
1.54.463.001 I slot print_timing: id  2 | task 440 |        eval time =    7104.43 ms /    44 tokens (  165.22 ms per token,     6.05 tokens per second)
1.54.463.009 I slot print_timing: id  2 | task 440 |       total time =    8135.07 ms /    90 tokens
1.54.463.011 I slot print_timing: id  2 | task 440 |    graphs reused =        455
1.54.464.280 I slot      release: id  2 | task 440 | stop processing: n_tokens = 219, truncated = 0
1.54.495.334 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.726 (> 0.100 thold), f_keep = 0.594
1.54.495.781 I slot launch_slot_: id  2 | task 485 | processing task, is_child = 0
2.01.389.094 I slot print_timing: id  2 | task 485 | prompt eval time =     998.22 ms /    49 tokens (   20.37 ms per token,    49.09 tokens per second)
2.01.389.103 I slot print_timing: id  2 | task 485 |        eval time =    5894.95 ms /    38 tokens (  159.32 ms per token,     6.28 tokens per second)
2.01.389.108 I slot print_timing: id  2 | task 485 |       total time =    6893.17 ms /    87 tokens
2.01.389.110 I slot print_timing: id  2 | task 485 |    graphs reused =        491
2.01.390.720 I slot      release: id  2 | task 485 | stop processing: n_tokens = 216, truncated = 0
2.01.435.558 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.720 (> 0.100 thold), f_keep = 0.606
2.01.436.254 I slot launch_slot_: id  2 | task 524 | processing task, is_child = 0
2.08.157.148 I slot print_timing: id  2 | task 524 | prompt eval time =     983.07 ms /    51 tokens (   19.28 ms per token,    51.88 tokens per second)
2.08.157.740 I slot print_timing: id  2 | task 524 |        eval time =    5737.43 ms /    43 tokens (  136.61 ms per token,     7.32 tokens per second)
2.08.157.749 I slot print_timing: id  2 | task 524 |       total time =    6720.50 ms /    94 tokens
2.08.157.755 I slot print_timing: id  2 | task 524 |    graphs reused =        532
2.08.157.924 I slot      release: id  2 | task 524 | stop processing: n_tokens = 224, truncated = 0
2.08.281.147 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.651 (> 0.100 thold), f_keep = 0.549
2.08.281.389 I slot launch_slot_: id  2 | task 568 | processing task, is_child = 0
2.17.011.423 I slot print_timing: id  2 | task 568 | prompt eval time =    1467.58 ms /    66 tokens (   22.24 ms per token,    44.97 tokens per second)
2.17.011.435 I slot print_timing: id  2 | task 568 |        eval time =    7262.40 ms /    52 tokens (  142.40 ms per token,     7.02 tokens per second)
2.17.011.437 I slot print_timing: id  2 | task 568 |       total time =    8729.98 ms /   118 tokens
2.17.011.439 I slot print_timing: id  2 | task 568 |    graphs reused =        582
2.17.014.414 I slot      release: id  2 | task 568 | stop processing: n_tokens = 240, truncated = 0
2.17.044.155 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.777 (> 0.100 thold), f_keep = 0.538
2.17.044.504 I slot launch_slot_: id  2 | task 621 | processing task, is_child = 0
2.19.271.151 I slot print_timing: id  2 | task 621 | prompt eval time =    1024.20 ms /    37 tokens (   27.68 ms per token,    36.13 tokens per second)
2.19.271.160 I slot print_timing: id  2 | task 621 |        eval time =    1202.39 ms /     9 tokens (  150.30 ms per token,     6.65 tokens per second)
2.19.271.161 I slot print_timing: id  2 | task 621 |       total time =    2226.59 ms /    46 tokens
2.19.271.163 I slot print_timing: id  2 | task 621 |    graphs reused =        589
2.19.272.862 I slot      release: id  2 | task 621 | stop processing: n_tokens = 174, truncated = 0
2.19.309.678 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.791 (> 0.100 thold), f_keep = 0.741
2.19.309.921 I slot launch_slot_: id  2 | task 631 | processing task, is_child = 0
2.23.662.472 I slot print_timing: id  2 | task 631 | prompt eval time =     904.04 ms /    34 tokens (   26.59 ms per token,    37.61 tokens per second)
2.23.662.483 I slot print_timing: id  2 | task 631 |        eval time =    3448.38 ms /    26 tokens (  137.94 ms per token,     7.25 tokens per second)
2.23.662.488 I slot print_timing: id  2 | task 631 |       total time =    4352.42 ms /    60 tokens
2.23.662.490 I slot print_timing: id  2 | task 631 |    graphs reused =        613
2.23.662.704 I slot      release: id  2 | task 631 | stop processing: n_tokens = 188, truncated = 0
2.23.684.268 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.709 (> 0.100 thold), f_keep = 0.686
2.23.684.493 I slot launch_slot_: id  2 | task 658 | processing task, is_child = 0
2.31.147.471 I slot print_timing: id  2 | task 658 | prompt eval time =     901.58 ms /    53 tokens (   17.01 ms per token,    58.79 tokens per second)
2.31.147.485 I slot print_timing: id  2 | task 658 |        eval time =    6561.34 ms /    44 tokens (  152.59 ms per token,     6.55 tokens per second)
2.31.148.055 I slot print_timing: id  2 | task 658 |       total time =    7462.92 ms /    97 tokens
2.31.148.086 I slot print_timing: id  2 | task 658 |    graphs reused =        655
2.31.148.299 I slot      release: id  2 | task 658 | stop processing: n_tokens = 225, truncated = 0
2.31.178.319 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.701 (> 0.100 thold), f_keep = 0.573
2.31.178.588 I slot launch_slot_: id  2 | task 703 | processing task, is_child = 0
2.38.324.003 I slot print_timing: id  2 | task 703 | prompt eval time =    1095.48 ms /    55 tokens (   19.92 ms per token,    50.21 tokens per second)
2.38.324.012 I slot print_timing: id  2 | task 703 |        eval time =    6049.86 ms /    38 tokens (  163.51 ms per token,     6.12 tokens per second)
2.38.324.014 I slot print_timing: id  2 | task 703 |       total time =    7145.35 ms /    93 tokens
2.38.324.588 I slot print_timing: id  2 | task 703 |    graphs reused =        691
2.38.324.692 I slot      release: id  2 | task 703 | stop processing: n_tokens = 221, truncated = 0
2.38.346.381 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.695 (> 0.100 thold), f_keep = 0.588
2.38.346.877 I slot launch_slot_: id  2 | task 742 | processing task, is_child = 0
2.52.066.687 I slot print_timing: id  2 | task 742 | prompt eval time =     953.81 ms /    57 tokens (   16.73 ms per token,    59.76 tokens per second)
2.52.067.015 I slot print_timing: id  2 | task 742 |        eval time =   12765.89 ms /    43 tokens (  303.95 ms per token,     3.29 tokens per second)
2.52.067.019 I slot print_timing: id  2 | task 742 |       total time =   13719.70 ms /   100 tokens
2.52.067.021 I slot print_timing: id  2 | task 742 |    graphs reused =        732
2.52.068.767 I slot      release: id  2 | task 742 | stop processing: n_tokens = 229, truncated = 0
2.53.101.287 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.305 (> 0.100 thold), f_keep = 0.572
2.53.101.742 I slot launch_slot_: id  2 | task 786 | processing task, is_child = 0
3.07.037.471 I slot print_timing: id  2 | task 786 | prompt eval time =    4383.97 ms /   298 tokens (   14.71 ms per token,    67.97 tokens per second)
3.07.037.502 I slot print_timing: id  2 | task 786 |        eval time =    9547.48 ms /    52 tokens (  187.21 ms per token,     5.34 tokens per second)
3.07.038.565 I slot print_timing: id  2 | task 786 |       total time =   13931.45 ms /   350 tokens
3.07.038.583 I slot print_timing: id  2 | task 786 |    graphs reused =        782
3.07.047.863 I slot      release: id  2 | task 786 | stop processing: n_tokens = 480, truncated = 0
3.07.209.712 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.909 (> 0.100 thold), f_keep = 0.769
3.07.211.845 I slot launch_slot_: id  2 | task 839 | processing task, is_child = 0
3.09.691.208 I slot print_timing: id  2 | task 839 | prompt eval time =    1071.12 ms /    37 tokens (   28.95 ms per token,    34.54 tokens per second)
3.09.691.220 I slot print_timing: id  2 | task 839 |        eval time =    1407.44 ms /     9 tokens (  175.93 ms per token,     5.68 tokens per second)
3.09.691.223 I slot print_timing: id  2 | task 839 |       total time =    2478.56 ms /    46 tokens
3.09.691.806 I slot print_timing: id  2 | task 839 |    graphs reused =        789
3.09.692.023 I slot      release: id  2 | task 839 | stop processing: n_tokens = 414, truncated = 0
3.09.737.859 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.916 (> 0.100 thold), f_keep = 0.891
3.09.738.161 I slot launch_slot_: id  2 | task 849 | processing task, is_child = 0
3.14.884.462 I slot print_timing: id  2 | task 849 | prompt eval time =     961.38 ms /    34 tokens (   28.28 ms per token,    35.37 tokens per second)
3.14.884.472 I slot print_timing: id  2 | task 849 |        eval time =    4184.86 ms /    30 tokens (  144.31 ms per token,     6.93 tokens per second)
3.14.884.473 I slot print_timing: id  2 | task 849 |       total time =    5146.25 ms /    64 tokens
3.14.884.518 I slot print_timing: id  2 | task 849 |    graphs reused =        817
3.14.884.621 I slot      release: id  2 | task 849 | stop processing: n_tokens = 432, truncated = 0
3.14.911.729 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.874 (> 0.100 thold), f_keep = 0.854
3.14.912.137 I slot launch_slot_: id  2 | task 880 | processing task, is_child = 0
3.23.798.478 I slot print_timing: id  2 | task 880 | prompt eval time =     977.18 ms /    53 tokens (   18.44 ms per token,    54.24 tokens per second)
3.23.798.494 I slot print_timing: id  2 | task 880 |        eval time =    7909.09 ms /    46 tokens (  175.76 ms per token,     5.69 tokens per second)
3.23.798.497 I slot print_timing: id  2 | task 880 |       total time =    8886.28 ms /    99 tokens
3.23.798.499 I slot print_timing: id  2 | task 880 |    graphs reused =        861
3.23.800.003 I slot      release: id  2 | task 880 | stop processing: n_tokens = 467, truncated = 0
3.23.843.278 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.870 (> 0.100 thold), f_keep = 0.790
3.23.843.617 I slot launch_slot_: id  2 | task 927 | processing task, is_child = 0
3.31.078.738 I slot print_timing: id  2 | task 927 | prompt eval time =    1011.44 ms /    55 tokens (   18.39 ms per token,    54.38 tokens per second)
3.31.078.750 I slot print_timing: id  2 | task 927 |        eval time =    6223.62 ms /    40 tokens (  159.58 ms per token,     6.27 tokens per second)
3.31.078.753 I slot print_timing: id  2 | task 927 |       total time =    7235.06 ms /    95 tokens
3.31.078.758 I slot print_timing: id  2 | task 927 |    graphs reused =        899
3.31.080.293 I slot      release: id  2 | task 927 | stop processing: n_tokens = 463, truncated = 0
3.31.112.328 I slot get_availabl: id  2 | task -1 | selected slot by LCP similarity, f_sim_best = 0.867 (> 0.100 thold), f_keep = 0.799
3.31.112.791 I slot launch_slot_: id  2 | task 968 | processing task, is_child = 0
3.39.000.204 I slot print_timing: id  2 | task 968 | prompt eval time =    1100.75 ms /    57 tokens (   19.31 ms per token,    51.78 tokens per second)
3.39.000.242 I slot print_timing: id  2 | task 968 |        eval time =    6786.48 ms /    42 tokens (  165.52 ms per token,     6.04 tokens per second)
3.39.000.256 I slot print_timing: id  2 | task 968 |       total time =    7887.23 ms /    99 tokens
3.39.000.259 I slot print_timing: id  2 | task 968 |    graphs reused =        939
3.39.002.553 I slot      release: id  2 | task 968 | stop processing: n_tokens = 468, truncated = 0
3.39.134.537 I slot get_availabl: id  1 | task -1 | selected slot by LRU, t_last = -1
3.39.136.339 I slot launch_slot_: id  1 | task 1011 | processing task, is_child = 0
3.51.898.243 I slot print_timing: id  1 | task 1011 | prompt eval time =    5364.43 ms /   451 tokens (   11.89 ms per token,    84.07 tokens per second)
3.51.898.254 I slot print_timing: id  1 | task 1011 |        eval time =    7362.72 ms /    52 tokens (  144.37 ms per token,     6.93 tokens per second)
3.51.898.257 I slot print_timing: id  1 | task 1011 |       total time =   12727.15 ms /   503 tokens
3.51.898.258 I slot print_timing: id  1 | task 1011 |    graphs reused =        989
3.51.900.731 I slot      release: id  1 | task 1011 | stop processing: n_tokens = 502, truncated = 0
3.51.938.577 I slot get_availabl: id  1 | task -1 | selected slot by LCP similarity, f_sim_best = 0.914 (> 0.100 thold), f_keep = 0.779
3.51.938.769 I slot launch_slot_: id  1 | task 1064 | processing task, is_child = 0
3.53.978.298 I slot print_timing: id  1 | task 1064 | prompt eval time =     911.09 ms /    37 tokens (   24.62 ms per token,    40.61 tokens per second)
3.53.978.309 I slot print_timing: id  1 | task 1064 |        eval time =    1128.39 ms /     9 tokens (  141.05 ms per token,     7.09 tokens per second)
3.53.978.310 I slot print_timing: id  1 | task 1064 |       total time =    2039.48 ms /    46 tokens
3.53.978.312 I slot print_timing: id  1 | task 1064 |    graphs reused =        996
3.53.978.358 I slot      release: id  1 | task 1064 | stop processing: n_tokens = 436, truncated = 0
3.53.999.657 I slot get_availabl: id  1 | task -1 | selected slot by LCP similarity, f_sim_best = 0.920 (> 0.100 thold), f_keep = 0.897
3.53.999.845 I slot launch_slot_: id  1 | task 1074 | processing task, is_child = 0
3.59.381.518 I slot print_timing: id  1 | task 1074 | prompt eval time =     906.57 ms /    34 tokens (   26.66 ms per token,    37.50 tokens per second)
3.59.381.529 I slot print_timing: id  1 | task 1074 |        eval time =    4475.04 ms /    30 tokens (  154.31 ms per token,     6.48 tokens per second)
3.59.381.532 I slot print_timing: id  1 | task 1074 |       total time =    5381.62 ms /    64 tokens
3.59.381.533 I slot print_timing: id  1 | task 1074 |    graphs reused =       1024
3.59.381.678 I slot      release: id  1 | task 1074 | stop processing: n_tokens = 454, truncated = 0
3.59.403.129 I slot get_availabl: id  1 | task -1 | selected slot by LCP similarity, f_sim_best = 0.881 (> 0.100 thold), f_keep = 0.861
3.59.403.443 I slot launch_slot_: id  1 | task 1105 | processing task, is_child = 0
4.07.328.522 I slot print_timing: id  1 | task 1105 | prompt eval time =    1010.81 ms /    53 tokens (   19.07 ms per token,    52.43 tokens per second)
4.07.328.535 I slot print_timing: id  1 | task 1105 |        eval time =    6914.20 ms /    46 tokens (  153.65 ms per token,     6.51 tokens per second)
4.07.328.538 I slot print_timing: id  1 | task 1105 |       total time =    7925.01 ms /    99 tokens
4.07.328.540 I slot print_timing: id  1 | task 1105 |    graphs reused =       1068
4.07.328.851 I slot      release: id  1 | task 1105 | stop processing: n_tokens = 489, truncated = 0
4.07.377.228 I slot get_availabl: id  1 | task -1 | selected slot by LCP similarity, f_sim_best = 0.877 (> 0.100 thold), f_keep = 0.800
4.07.377.635 I slot launch_slot_: id  1 | task 1152 | processing task, is_child = 0
4.14.097.760 I slot print_timing: id  1 | task 1152 | prompt eval time =     962.58 ms /    55 tokens (   17.50 ms per token,    57.14 tokens per second)
4.14.097.770 I slot print_timing: id  1 | task 1152 |        eval time =    5757.45 ms /    40 tokens (  147.63 ms per token,     6.77 tokens per second)
4.14.097.773 I slot print_timing: id  1 | task 1152 |       total time =    6720.03 ms /    95 tokens
4.14.097.775 I slot print_timing: id  1 | task 1152 |    graphs reused =       1106
4.14.097.989 I slot      release: id  1 | task 1152 | stop processing: n_tokens = 485, truncated = 0
4.14.121.237 I slot get_availabl: id  1 | task -1 | selected slot by LCP similarity, f_sim_best = 0.873 (> 0.100 thold), f_keep = 0.808
4.14.121.680 I slot launch_slot_: id  1 | task 1193 | processing task, is_child = 0
4.21.849.631 I slot print_timing: id  1 | task 1193 | prompt eval time =    1086.43 ms /    57 tokens (   19.06 ms per token,    52.47 tokens per second)
4.21.849.643 I slot print_timing: id  1 | task 1193 |        eval time =    6641.44 ms /    42 tokens (  161.99 ms per token,     6.17 tokens per second)
4.21.849.645 I slot print_timing: id  1 | task 1193 |       total time =    7727.88 ms /    99 tokens
4.21.849.646 I slot print_timing: id  1 | task 1193 |    graphs reused =       1146
4.21.849.791 I slot      release: id  1 | task 1193 | stop processing: n_tokens = 490, truncated = 0
4.21.904.861 I slot get_availabl: id  0 | task -1 | selected slot by LRU, t_last = -1
4.21.904.937 I slot launch_slot_: id  0 | task 1236 | processing task, is_child = 0
4.34.902.872 I slot print_timing: id  0 | task 1236 | prompt eval time =    5127.33 ms /   442 tokens (   11.60 ms per token,    86.20 tokens per second)
4.34.902.884 I slot print_timing: id  0 | task 1236 |        eval time =    7841.69 ms /    52 tokens (  153.76 ms per token,     6.50 tokens per second)
4.34.902.886 I slot print_timing: id  0 | task 1236 |       total time =   12969.01 ms /   494 tokens
4.34.902.890 I slot print_timing: id  0 | task 1236 |    graphs reused =       1196
4.34.904.599 I slot      release: id  0 | task 1236 | stop processing: n_tokens = 493, truncated = 0
4.34.932.476 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 0.912 (> 0.100 thold), f_keep = 0.775
4.34.932.812 I slot launch_slot_: id  0 | task 1289 | processing task, is_child = 0
4.37.516.846 I slot print_timing: id  0 | task 1289 | prompt eval time =    1021.43 ms /    37 tokens (   27.61 ms per token,    36.22 tokens per second)
4.37.516.859 I slot print_timing: id  0 | task 1289 |        eval time =    1562.53 ms /     9 tokens (  195.32 ms per token,     5.12 tokens per second)
4.37.516.862 I slot print_timing: id  0 | task 1289 |       total time =    2583.96 ms /    46 tokens
4.37.516.865 I slot print_timing: id  0 | task 1289 |    graphs reused =       1203
4.37.517.024 I slot      release: id  0 | task 1289 | stop processing: n_tokens = 427, truncated = 0
4.37.544.645 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 0.918 (> 0.100 thold), f_keep = 0.895
4.37.544.986 I slot launch_slot_: id  0 | task 1299 | processing task, is_child = 0
4.45.247.219 I slot print_timing: id  0 | task 1299 | prompt eval time =    1009.77 ms /    34 tokens (   29.70 ms per token,    33.67 tokens per second)
4.45.247.232 I slot print_timing: id  0 | task 1299 |        eval time =    6692.38 ms /    30 tokens (  230.77 ms per token,     4.33 tokens per second)
4.45.247.235 I slot print_timing: id  0 | task 1299 |       total time =    7702.15 ms /    64 tokens
4.45.247.238 I slot print_timing: id  0 | task 1299 |    graphs reused =       1231
4.45.247.394 I slot      release: id  0 | task 1299 | stop processing: n_tokens = 445, truncated = 0
4.45.273.107 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 0.878 (> 0.100 thold), f_keep = 0.858
4.45.273.483 I slot launch_slot_: id  0 | task 1330 | processing task, is_child = 0
4.53.643.645 I slot print_timing: id  0 | task 1330 | prompt eval time =    1017.36 ms /    53 tokens (   19.20 ms per token,    52.10 tokens per second)
4.53.643.654 I slot print_timing: id  0 | task 1330 |        eval time =    7352.73 ms /    46 tokens (  163.39 ms per token,     6.12 tokens per second)
4.53.643.657 I slot print_timing: id  0 | task 1330 |       total time =    8370.09 ms /    99 tokens
4.53.643.659 I slot print_timing: id  0 | task 1330 |    graphs reused =       1275
4.53.643.969 I slot      release: id  0 | task 1330 | stop processing: n_tokens = 480, truncated = 0
4.53.672.234 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 0.874 (> 0.100 thold), f_keep = 0.796
4.53.672.547 I slot launch_slot_: id  0 | task 1377 | processing task, is_child = 0
5.01.386.264 I slot print_timing: id  0 | task 1377 | prompt eval time =    1049.05 ms /    55 tokens (   19.07 ms per token,    52.43 tokens per second)
5.01.386.301 I slot print_timing: id  0 | task 1377 |        eval time =    6664.61 ms /    40 tokens (  170.89 ms per token,     5.85 tokens per second)
5.01.386.305 I slot print_timing: id  0 | task 1377 |       total time =    7713.66 ms /    95 tokens
5.01.386.308 I slot print_timing: id  0 | task 1377 |    graphs reused =       1313
5.01.386.582 I slot      release: id  0 | task 1377 | stop processing: n_tokens = 476, truncated = 0
5.01.416.017 I slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 0.870 (> 0.100 thold), f_keep = 0.805
5.01.416.422 I slot launch_slot_: id  0 | task 1418 | processing task, is_child = 0
5.09.308.317 I slot print_timing: id  0 | task 1418 | prompt eval time =    1073.15 ms /    57 tokens (   18.83 ms per token,    53.11 tokens per second)
5.09.308.329 I slot print_timing: id  0 | task 1418 |        eval time =    6818.66 ms /    42 tokens (  166.31 ms per token,     6.01 tokens per second)
5.09.308.333 I slot print_timing: id  0 | task 1418 |       total time =    7891.81 ms /    99 tokens
5.09.308.335 I slot print_timing: id  0 | task 1418 |    graphs reused =       1353
5.09.308.596 I slot      release: id  0 | task 1418 | stop processing: n_tokens = 481, truncated = 0

```