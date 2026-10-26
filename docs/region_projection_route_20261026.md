# P125 後の次候補と、成立していない主張

P125 は各方式 3/4 成功、各 766,875 token で一致し、全 146 program で自動射影が発動しなかった。従来 library provider では実際の 25 show_song 要求に必要な値が先に存在せず、ID も全件既観測だった。構文制限の緩和や ID guard の追加だけを根拠に同じ比較を繰り返さない。

閉鎖後に既実装の `JoinedPublicReadAuthority` まで調べると、必要な title/artists が先にそろう要求は各 13/25 件だった。先行 show_song 返答を一切使わない場合は 10、利用可能な要求だけを省く有限 prefix の感度分析では 13 候補が残る。これらは通常の結合再利用の機会で、実 API 削減や token 削減の測定ではない。元記録の最後の要求は、実 loop の最終反復とは限らない。

次候補は、この通常 joined-demand reuse を比較対象にも与え、元の call_api コードが限定した consumer だけを持つ場合に、ハーネスが loop 入口の exact builtin 値・binding・alias・scope を検査して自動適用する追加差である。検査失敗時はその位置の元 loop へ続け、実行済み prefix を再実行しない。真の最終反復では元位置で完全値を取得し、partial 後の例外・契約失敗は明示した停止規則に従う。一般 Python の意味保存や外部 API の無条件な省略を保証するものではない。

guard により通常 loop と最適化 loop を選ぶ構成は既知である。[LLVM の LoopVersioningLICM 実装](https://llvm.org/doxygen/LoopVersioningLICM_8cpp_source.html)。partial redundancy elimination と制御フロー変更を組み合わせる研究もある。[Bodik・Gupta・Soffa, Complete Removal of Redundant Expressions, 著者要旨](https://people.cs.pitt.edu/~soffa/research/Comp/pldi98.html)。今回の確認はその設計説明・要旨までで、従来方式の全再現ではない。対象を LLM 生成 Python に変えたことや既存 join を接続したことだけを新規性としない。

普通の explicit field-demand 能力、guide、cache、scope/epoch、rolling separate checkpoint、予算を両側でそろえ、自動適用の有無だけを比較する。通常側が同じ需要再利用を使って差が消えれば、追加価値は示せていない。

内部 API を 13 件省いても、それらが同じ program 内にあれば LLM 呼出しは直接消えない。直接の token 経路は receipt / 予算通知の表示差である。API 上限回避後の作業・生成・成功・全 job 費用は新しい固定比較で測る。成功まで続けて元の安い失敗より費用が増えた場合、それを品質維持の token 削減と呼ばない。

試作と合成反証、未来値を使わない固定 offline 確認を先に行う。有限の全条件比較を固定するまでモデル実験を開始せず、途中結果に応じた seed・scope・guide・予算の変更はしない。現時点ではこの候補の技術的新規性、全 job token 削減、未見課題の品質維持、レター採択に必要な貢献は未成立である。
