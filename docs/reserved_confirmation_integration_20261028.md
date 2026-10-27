# 保留12課題の確認実験に向けた接続準備

この変更は再利用可能な準備部品の公開を目的とする。実験の採用、候補方式・seed・予算の決定、起動計画の固定は行っていない。実予約のID一覧・課題本文・data・gold、進行中P141の成果・usage・生成物は読まず、モデル・環境・native計数・評価も実行していない。過去の開発結果やP141の単一課題診断を未見確認へ読み替えない。

[予定表helper](../scripts/reserved_confirmation_schedule.py)は、呼出側が原bytesと順序を認証した全12の予約metadataから、2方式×各1回の24枠を組み立てるpure関数である。12の別scenario・variant1を全て保持し、元順序の奇数課題はbaseline先行、偶数課題はcandidate先行とする。単一seedと全枠共通の明示budgetを要求し、欠枠・subset・並替え・異なる引数への差替えを拒否する。認証済み予約を読込む機能や候補の適格性判定は含まない。

[初期状態helper](../scripts/reserved_confirmation_initial_state.py)は、12 reference worldと24 cell worldのinit commandを構成するpure adapterである。呼出側が認証したtyped init receiptと正常cleanupを全12件揃えてprivate bundleへ束縛し、後のcell初期化を対応するreferenceの公開projectionと照合する。既知開発用の `source_run` や `known_public_task_sha256` を捏造しない。このbundleには課題文やアカウント情報が含まれ得るため公開成果物ではない。projection一致だけでは、DB全体の同一性・receiptの真正性・所有process・freshnessは証明されない。

[reference-provider](../scripts/reserved_confirmation_reference_provider.py)と対応testは独立source peerを通過した版を同bytesで追加した。import時やCLIからの自動実行はなく、将来明示的に呼び出すと、固定入力・新namespace・有限leaseを検査してreference12件を順番に初期化しcloseする。最初の失敗で止まり、自動retryしない。候補bundle fileはfinalization失敗でも残り得るため、後続処理にはterminal `status=complete`、`bundle_accepted=true`、`within_total_lease=true`、`all_owned_processes_stopped=true`の全てと束縛hashの確認が必要で、fileの存在だけでは使用しない。合成検証とsource peerは、実予約データの適格性や実環境接続の成功を意味しない。

実launcherには次の接続が残る。認証済みの原予約と曝露履歴、候補・対照の適格性、source/protocol/seed/budgetを結果非依存に固定する。新workerは開発用保存runではなくfresh init receiptとprivate bundleを入口にし、最初のactor入力・toolsを両方式で同じ規則から生成する。preflightはその入口からnative count/send等のbindingを検証し、実予約へアクセスした事実を正しく記録する。新namespaceのdriver・有限server lease・停止/cleanup・監査・集計を全24予定枠へ接続し、失敗・未実施・unknownを保持する。既存P140/P141 workerの既知課題前提やphase固定を、そのまま新課題へ流用しない。

**setup費用は24cell分だけではない。** reference12回とcell24回で初期化は最大36回となる。1回のreference setup/cleanup上限をS/Cとするなら、少なくとも `12×(S+C)` の予約枠がcell予算の外に必要である。各cellのwork/setup/cleanup/idle/evaluation上限をW/S/C/I/Vと共通化する場合、直列予約の基本形は `24×(W+S+C+I+V)+12×(S+C)` で、preflight・server起動/停止・後処理・全体記録等の未包含分も別途上限と記録を持たせる。reference-providerではbridge起動とinitをSに、close/exit待ち・必要時terminate/kill・資源closeをCに含め、reference folderやbundleの書込み等もtotal wallの対象となる。終端記録の保存までを含めた外側の終了処理には別途余白を設ける。OS・filesystem操作のhard realtime中断までは保証しないため、setup/cleanup上限の和だけで総leaseを使い切らない。これは実行時間の予測や確約ではない。referenceは生成を行わなくてもwall費用があり、失敗したsetupとcleanupも保存する。有限予算と終了上限が固定されるまで、この部品群だけでは起動できない。
