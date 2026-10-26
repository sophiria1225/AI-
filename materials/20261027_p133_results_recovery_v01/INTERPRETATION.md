# P133の会計と解釈

全4枠は既知CSV1課題×通常rolling_separate/empirical_payback×seeds57/157。各方式434,623 logical input+output tokens、各1/2成功。全869,246 tokensは全usageが既知のため確定できる。共通成功1 pairの差も全仕事差も0、実payback拒否0、固定gate false。unknown0であっても、一般的品質や因果効果を証明したことにはならない。

全82 model呼出しにactor78とfocus4を含む。cached inputを費用から差し引かない。各方式seed57のfocus41,075 tokensをactor291,513へ加算する。seed157は各方式API80上限で失敗しfocus0だった。失敗費用、無効な制御、要約費用を除かない。今回、shadow拒否と実拒否はいずれも0であり、予測拒否後の品質・費用は未観測である。

server全体は3,835.621秒、cell全体は3,738.419秒、評価は6.365秒。setup/work/要約/制御/評価/cleanupの区間は重なるので加算して新しい総時間を作らない。report-only回収の時間は別の運用証拠に保存し、元serverやmodel費用を書き換えない。今回のwall差を速度優位として採用しない。

元reportが固定公開pathを拒否した失敗と、別data-only回収を区別する。元audit/sessionのbytesを使い、純粋な行整形・採否関数は共有した。独立検算もnative履歴再構成を固定producer auditorに依存する範囲があり、完全に別実装による意味保存証明ではない。公開されるのは集約、判定、hash、図であり、task値、reasoning、生成code、認証、独立評価本文を含めない。
