# 途中の計数、終端使用量、実行できるメッセージを分ける

固定したllama.cpp `620d2225cc436ab0b001e3200e590e3b286ef9ab`（b11669）の説明と該当実装を確認した。全リポジトリの検証ではない。

[固定ファイル・読解範囲・ハッシュ](../reports/stream_receipt_sources_20261022.json)。取得した７ファイルのGit blob照合は一致したが、キャッシュした全行を読んだという意味ではない。

- [server-common.cpp](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/tools/server/server-common.cpp#L84)の`prompt_n`は実処理入力、`cache_n`はキャッシュ入力、`predicted_n`はその時点の累積出力。
- [server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/tools/server/server-context.cpp#L2187)は途中の応答に計数を載せる。[server-task.cpp](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/tools/server/server-task.cpp#L480)では終了理由とusageを別のストリーム片で返す。改行だけを読んだり、最後の途中計数を終端としたりすると区別が失われる。
- [生成時間制限の判定](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/tools/server/server-context.cpp#L2080)は改行時に行う。最初のtokenより前の処理も含めた厳密な壁時計制限としては使わない。
- [README](https://github.com/ggml-org/llama.cpp/blob/620d2225cc436ab0b001e3200e590e3b286ef9ab/tools/server/README.md)には出力上限のマルチバイト文字に関する注意もある。予約上限を確定使用量と呼ばず、実際の終端計数を検証する。

追加した受信器はUTF-8の分割、CRLF、複数のデータ行、応答ID、単一choice、増加する計数、ツール呼出しごとの断片を検査する。対応するSSEはこの固定版のdata行とコメント行に限定し、一般の全SSE機能を実装したとはしない。

途中切断時は入力・出力の確定値をnullのままにし、確認できた出力の下限と途中処理情報を保存する。入力下限０も「実際の入力０」を意味しない。終端usageが検証できてもDONEがなければ、費用だけを保持してメッセージは返さない。完全なメッセージでも、通常の引数・権限・予算の検査は別に必要である。

原記録は非公開ディレクトリへ逐次保存する。保存の時間は測定時間に含めるが、電源断に対する永続化保証はしない。凍結済みの`local_llama.py`と過去の実験は変更しない。合成例で検査後、[P51の３回だけの校正](experiments/P51_stream_receipts.md)で実サーバーとの対応を調べる。
