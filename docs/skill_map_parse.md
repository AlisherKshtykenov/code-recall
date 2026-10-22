
**Models**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| — | `linear_regression` | модель-блок | 1 |
| — | `ridge` | модель-блок | 1 |
| — | `lasso` | модель-блок | 1 |
| — | `decision_tree` | модель-блок | 1 |
| — | `random_forest` | модель-блок | 1 |
| — | `gradient_boosting` | модель-блок | 1 |
| — | `logistic_regression` | модель-блок | 1 |
| — | `svm` | модель-блок | 1 |
| — | `kmeans` | модель-блок | 1 |
| — | `dbscan` | модель-блок | 1 |
| — | `gaussian_mixture` | модель-блок | 1 |
| — | `autoencoder` | модель-блок | 1 |
| — | `resnet` | модель-блок | 2 |
| — | `efficientnet` | модель-блок | 2 |
| — | `vit` | модель-блок | 1 |
| — | `unet` | модель-блок | 1 |
| — | `deeplab` | модель-блок | 1 |
| — | `facenet` | модель-блок | 1 |
| — | `arcface` | модель-блок | 1 |
| — | `lstm` | модель-блок | 2 |
| — | `bert` | модель-блок | 1 |
| — | `arima` | модель-блок | 1 |
| — | `prophet` | модель-блок | 1 |
| — | `tacotron2` | модель-блок | 1 |
| — | `fastspeech` | модель-блок | 1 |
| — | `vits` | модель-блок | 1 |
| — | `hifigan` | модель-блок | 1 |
| — | `ctc_lstm` | модель-блок | 1 |
| — | `whisper` | модель-блок | 1 |
| — | `gan` | модель-блок | 1 |
| — | `vae` | модель-блок | 1 |
| — | `diffusion` | модель-блок | 1 |
| — | `baseline_cnn` | модель-блок | 1 |

**Preprocessing**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| scaling | `standard_scaler` | кирпичик | 5 |
| missing | `simple_imputer` | кирпичик | 2 |
| encoding · encoding (scaling не нужен) | `one_hot_encoder` | кирпичик | 3 |
| imbalance · class_weights | `class_weights` | кирпичик | 2 |
| outliers | `iqr_outliers` | кирпичик | 1 |
| normalization картинок · normalize_images | `normalize_images` | кирпичик | 2 |
| splitting | `train_test_split` | кирпичик | 2 |
| splitting по людям (group_kfold) | `group_kfold` | кирпичик | 1 |
| encoding (токены) | `tokenizer` | кирпичик | 1 |
| missing (ffill) | `forward_fill` | кирпичик | 1 |
| transformation | `differencing` | кирпичик | 1 |
| нормализация текста | `text_normalization` | кирпичик | 1 |
| аудио · аудио признаки | `mel_spectrogram` | кирпичик | 2 |
| scaling в [-1,1] | `minmax_scaler` | кирпичик | 1 |
| — | `stratified_split` | кирпичик | 1 |

**Layers**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| dense (1 слой) · dense · dense (эмбеддинг) · linear | `linear` | кирпичик | 6 |
| conv · conv2d | `conv2d` | кирпичик | 6 |
| pooling · max_pool2d | `max_pool2d` | кирпичик | 2 |
| — | `batch_norm` | кирпичик | 2 |
| residual | `residual_block` | слот-вариант | 2 |
| — | `attention` | слот-вариант | 5 |
| conv_transpose | `conv_transpose2d` | кирпичик | 2 |
| — | `skip_connection` | кирпичик | 1 |
| — | `embedding` | кирпичик | 2 |
| recurrent | `lstm_layer` | слот-вариант | 3 |
| — | `layer_norm` | кирпичик | 1 |
| — | `conv1d` | кирпичик | 2 |
| — | `dropout` | кирпичик | 1 |
| — | `flatten` | кирпичик | 1 |

**Activations**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| — | `identity` | слот-вариант `activation` | 2 |
| sigmoid · sigmoid на выходе | `sigmoid` | слот-вариант `activation` | 4 |
| — | `softmax` | слот-вариант `activation` | 4 |
| — | `relu` | слот-вариант `activation` | 7 |
| — | `gelu` | слот-вариант `activation` | 3 |
| — | `tanh` | слот-вариант `activation` | 4 |
| — | `leaky_relu` | слот-вариант `activation` | 1 |

**Losses**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| — | `mse` | слот-вариант `loss` | 3 |
| — | `mae` (также Metrics) | слот-вариант `loss` | 3 |
| — | `huber` | слот-вариант `loss` | 2 |
| — | `log_loss` | слот-вариант `loss` | 2 |
| — | `cross_entropy` | слот-вариант `loss` | 5 |
| focal | `focal_loss` | слот-вариант `loss` | 1 |
| hinge | `hinge_loss` | слот-вариант `loss` | 1 |
| — | `inertia` | слот-вариант `loss` | 1 |
| likelihood | `log_likelihood` | слот-вариант `loss` | 1 |
| reconstruction · reconstruction error | `reconstruction_error` (также Metrics) | слот-вариант `loss` | 1 |
| kl_divergence (vae) · kl_divergence | `kl_divergence` | слот-вариант `loss` | 2 |
| dice | `dice_loss` | слот-вариант `loss` | 1 |
| triplet | `triplet_loss` | слот-вариант `loss` | 1 |
| arcface | `arcface_loss` | слот-вариант `loss` | 1 |
| contrastive | `contrastive_loss` | слот-вариант `loss` | 1 |
| mel_spectrogram · mel-ошибка | `mel_loss` (также Metrics) | слот-вариант `loss` | 1 |
| adversarial | `adversarial_loss` | слот-вариант `loss` | 2 |
| ctc | `ctc_loss` | слот-вариант `loss` | 1 |
| diffusion | `diffusion_loss` — MSE между настоящим и предсказанным шумом, связан с моделью `diffusion` | слот-вариант `loss` | 1 |
| — | `weighted_cross_entropy` | слот-вариант `loss` | 1 |

**Optimizers**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| — | `batch_gd` | слот-вариант `optimizer` | 1 |
| sgd · sgd (momentum) | `sgd` | слот-вариант `optimizer` | 3 |
| — | `lbfgs` | слот-вариант `optimizer` | 2 |
| бустинг по деревьям | `boosting_trees` | концепт | 1 |
| — | `adam` | слот-вариант `optimizer` | 8 |
| — | `second_order` | концепт | 1 |
| SMO | `smo` | концепт | 1 |
| итерации EM | `em_iterations` | концепт | 1 |
| — | `adamw` | слот-вариант `optimizer` | 3 |
| — | `cosine_annealing` | кирпичик (scheduler) | 1 |
| — | `warmup` | кирпичик (scheduler) | 2 |

**Metrics**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| — | `mae` (также Losses) | слот-вариант `metric` | 3 |
| — | `rmse` | слот-вариант `metric` | 2 |
| — | `r2` | слот-вариант `metric` | 2 |
| — | `f1` | слот-вариант `metric` | 5 |
| — | `roc_auc` | слот-вариант `metric` | 3 |
| — | `pr_auc` | слот-вариант `metric` | 2 |
| — | `silhouette` | слот-вариант `metric` | 1 |
| — | `davies_bouldin` | слот-вариант `metric` | 1 |
| — | `ari` | слот-вариант `metric` | 1 |
| reconstruction · reconstruction error | `reconstruction_error` (также Losses) | слот-вариант `metric` | 1 |
| accuracy · accuracy верификации | `accuracy` | слот-вариант `metric` | 3 |
| — | `iou` | слот-вариант `metric` | 1 |
| dice | `dice_score` | слот-вариант `metric` | 1 |
| — | `mape` | слот-вариант `metric` | 1 |
| — | `mos` | концепт | 1 |
| mel_spectrogram · mel-ошибка | `mel_loss` (также Losses) | слот-вариант `metric` | 1 |
| — | `wer` | слот-вариант `metric` | 1 |
| — | `cer` | слот-вариант `metric` | 1 |
| — | `fid` | слот-вариант `metric` | 1 |
| — | `recall` | слот-вариант `metric` | 1 |
| — | `confusion_matrix` | слот-вариант `metric` | 1 |

**Comparison**

| Исходный текст | Имя | Тип | Строк |
|---|---|---|---|
| cross_validation | `cross_val_score` | кирпичик | 2 |
| dummy_mean | `dummy_regressor` | кирпичик | 1 |
| — | `grid_search` | кирпичик | 2 |
| stratified cv | `stratified_kfold` | кирпичик | 2 |
| dummy_most_frequent | `dummy_classifier` | кирпичик | 2 |
| mcnemar | `mcnemar_test` | кирпичик | 1 |
| — | `elbow_method` | кирпичик | 1 |
| silhouette по k | `silhouette_by_k` | кирпичик | 1 |
| ablation по размеру · ablation | `ablation` | кирпичик | 4 |
| — | `learning_curve` | кирпичик | 3 |
| scratch vs pretrained | `scratch_vs_pretrained` | концепт | 1 |
| benchmark_table · leaderboard | `benchmark_table` | кирпичик | 4 |
| — | `bootstrap_ci` | кирпичик | 1 |
| — | `time_series_split` | кирпичик | 1 |
| simple_model (наивный прогноз) | `naive_forecast` | концепт | 1 |
| — | `holdout_eval` | кирпичик | 1 |

всего уникальных: 134 {'brick': 94, 'model': 33, 'concept': 7}
