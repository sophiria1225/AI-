# 外部の履歴実装を確認

smolagents の固定版で、呼出しIDをモデル向け本文へ入れる通常経路と、本文解析時にUUIDを作る経路をソースから確認した. CodeAgentでは手順番号由来のIDを使うことも残し、すべての経路を乱数ID扱いしない.

[確認した範囲と限界](../../docs/external_history_identifier_review_20261024.md)／[固定出典とhash](../../reports/external_history_identifier_sources_20261024.json).

外部フレームワークの実行、モデル生成、環境API、課題評価は０. 外部での性能変化・因果効果は未計測. 現在の [P98原稿](../../papers/202610_letter/execution_evidence_cohort/README.md) には未統合の補足で、新規手法の成立や採録見込みの保証ではない.
