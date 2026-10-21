"""Presentation narrative from a concrete task to the audited handoff experiment.

No experimental configuration or in-progress trace is read here. Illustrations
are explicitly distinguished from measurements on the four development tasks.
"""
import html

LINK = 'https://github.com/sophiria1225/AI-/blob/main/'
INK, TEAL, RUST, MUTED = '#172c43', '#167a78', '#c95c33', '#596c79'
ARMS = ('full_keep', 'recent_keep', 'full_reset', 'recent_reset')
NAMES = ('A 全履歴＋保持', 'B 直近＋保持', 'C 全履歴＋初期化', 'D 直近＋初期化')


def text(x, y, label, size=23, color=INK, anchor='start', bold=False):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" '
            f'text-anchor="{anchor}" font-weight="{700 if bold else 500}">{html.escape(str(label))}</text>')


def arrow(x1, y1, x2, y2, color=TEAL):
    return (f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="{color}" '
            'stroke-width="3" marker-end="url(#story-arrow)"/>')


def svg(body, label, height=360):
    return (f'<svg viewBox="0 0 1120 {height}" role="img" aria-label="{html.escape(label)}" '
            'xmlns="http://www.w3.org/2000/svg"><defs><marker id="story-arrow" '
            'markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto">'
            f'<path d="M0 0 L8 4 L0 8" fill="{TEAL}"/></marker></defs>{body}</svg>')


def photo_workflow():
    s = text(10, 28, '例：写真を撮影日ごとのフォルダーへ整理する', 25, bold=True)
    for i, (x, title, sub) in enumerate([(45, '一覧を取得', '何が対象か'), (330, '撮影日を確認', 'どこへ移すか'),
                                        (615, '写真を移動', '実際に変更'), (900, '完了を確認', '要求を満たしたか')]):
        if i < 2:
            for j in range(3):
                xx = x + 10 + j * 30
                s += f'<rect x="{xx}" y="82" width="83" height="75" rx="5" fill="#e0ebe5" stroke="{TEAL}" stroke-width="2"/>'
                s += f'<path d="M{xx+9} 145 l23-29 16 19 13-14 14 24" fill="none" stroke="{TEAL}" stroke-width="2"/>'
            if i == 1:
                s += text(x+81, 189, '日付 → 移動先', 19, TEAL, 'middle')
        else:
            s += f'<path d="M{x+9} 94 h55 l12 13 h97 v74 h-164z" fill="#e0ebe5" stroke="{TEAL}" stroke-width="3"/>'
            s += text(x+90, 151, '移動先' if i == 2 else '✓', 25, TEAL, 'middle', True)
        s += text(x+88, 237, title, 26, INK, 'middle', True)
        s += text(x+88, 275, sub, 21, MUTED, 'middle')
        if i < 3:
            s += arrow(x+190, 129, x+263, 129)
    s += text(10, 335, 'この間に、取得した値・判断・操作済みの内容をつなぐ必要がある。', 24, bold=True)
    return svg(s, '写真整理の四工程と、それをつなぐ情報', 365)


def missing_context():
    s = text(10, 27, '説明用の場面：途中で会話履歴を短くして再開する', 23, MUTED)
    s += '<path d="M20 70h470v125H65l-30 25v-25H20z" fill="#e0ebe5"/>'
    s += text(45, 110, '「一覧を取得した。撮影日で分類した。', 24)
    s += text(45, 151, '次は、未処理の写真を移動する」', 24)
    s += arrow(510, 130, 595, 130)
    s += '<path d="M620 70h480v125H665l-30 25v-25h-15z" fill="#eee1d7"/>'
    s += text(645, 110, '再開したAIに見えるのは直近の結果だけ', 23)
    s += text(645, 151, '「残っている一覧は何に使うもの？」', 24, RUST, bold=True)
    s += text(20, 274, '値が残ること', 29, TEAL, bold=True)
    s += text(270, 274, '≠', 36, MUTED)
    s += text(350, 274, '用途・作業の続きが伝わること', 29, RUST, bold=True)
    s += text(20, 326, '想定される支障：調べ直す／計算し直す／処理を抜かす／重複して処理する', 22)
    return svg(s, '値の保持と作業意図の引き継ぎは別という問題の説明例', 350)


def three_states():
    s = ''
    for x, label, color in [(15, '① 会話履歴', TEAL), (400, '② Pythonの変数', TEAL), (785, '③ アプリの状態', MUTED)]:
        s += text(x, 35, label, 27, color, bold=True)
        s += f'<line x1="{x}" y1="58" x2="{x+320}" y2="58" stroke="{color}" stroke-width="4"/>'
    for x, lines in [(15, ['AIの過去の応答', 'ツールが返した結果', '次の入力としてAIに見せる']),
                     (400, ['取得した一覧や計算結果', '実行環境にある値', 'コードで再利用できる']),
                     (785, ['移動済みのファイル', '送信済みの依頼や返金', 'すでに実行した操作の結果'])]:
        for j, label in enumerate(lines):
            s += text(x, 105+j*45, label, 23)
    s += text(15, 274, '今回、全部／直近に変える', 22, TEAL, bold=True)
    s += text(400, 274, '今回、保持／初期化に変える', 22, TEAL, bold=True)
    s += text(785, 274, '全条件で同じ状態から開始', 22, MUTED, bold=True)
    s += text(15, 335, '変数を消しても、すでに移動した写真は元に戻さない。', 25, bold=True)
    return svg(s, '会話履歴、Python変数、アプリの状態の区別', 360)


def harness_architecture():
    s = text(10, 25, '利用者の要求', 23, bold=True)
    s += arrow(140, 18, 230, 18)
    s += text(255, 25, 'ハーネス：次の入力と実行手順を管理するプログラム', 24, TEAL, bold=True)
    for x, title, sub in [(135, '入力を組む', '要求＋会話履歴'), (545, 'AIがコードを生成', '次の調査・計算・操作'),
                           (955, 'Pythonで実行', '変数を保持・APIを操作')]:
        s += f'<circle cx="{x}" cy="145" r="62" fill="#e0ebe5"/>'
        s += text(x, 154, '①' if x == 135 else '②' if x == 545 else '③', 38, TEAL, 'middle', True)
        s += text(x, 248, title, 26, INK, 'middle', True)
        s += text(x, 287, sub, 21, MUTED, 'middle')
    s += arrow(210, 145, 470, 145)+arrow(620, 145, 880, 145)
    s += '<path d="M955 319 V357 H135 V319" fill="none" stroke="#167a78" stroke-width="3" marker-end="url(#story-arrow)"/>'
    s += text(545, 345, '実行結果を履歴へ追加し、次の判断へ', 22, TEAL, 'middle')
    return svg(s, '要求から入力構成、AIのコード生成、Pythonとアプリ操作、結果の再入力まで', 380)


def fork_protocol():
    s = text(15, 27, '共通の前半', 26, bold=True)
    for i in range(4):
        x = 65+i*96
        s += f'<circle cx="{x}" cy="101" r="27" fill="#e0ebe5"/>'
        s += text(x, 109, str(i+1), 24, TEAL, 'middle', True)
        if i < 3:
            s += arrow(x+29, 101, x+65, 101)
    s += text(15, 164, 'AIの応答 → ツール実行 を４回', 22)
    s += text(15, 204, 'この時点で会話・変数・環境を保存', 21)
    s += text(15, 257, '成功・失敗を見て地点を選ばない', 21, MUTED)
    s += arrow(405, 101, 478, 101)
    s += '<path d="M480 57 V294" fill="none" stroke="#167a78" stroke-width="3"/>'
    for i, (letter, short) in enumerate(zip('ABCD', ['全履歴＋保持', '直近＋保持', '全履歴＋初期化', '直近＋初期化'])):
        y = 57+i*79
        s += arrow(480, y, 530, y)
        s += text(555, y+8, letter+'  '+short, 23, bold=True)
        s += arrow(800, y, 870, y)
        s += text(900, y+8, '継続 → 評価', 23)
    s += text(15, 351, '４課題 × ４条件 × 各１回 ＝ 16実行。独立した課題数は４件。', 25, bold=True)
    return svg(s, '一つの途中状態を四条件に分けて継続する実験手順', 380)


def cost_chart(handoff, diagnostics):
    totals = handoff['totals']
    first = {a: sum(r['first_continuation_input_tokens'] for r in diagnostics['rows'] if r['arm'] == a) for a in ARMS}
    s = ''
    for x, width, heading, values, note in [
        (15, 430, '再開直後の入力', [first['full_keep'], first['recent_keep']], '４課題の最初の１入力の合計'),
        (610, 430, '終了までの総トークン', [totals['full_keep']['known_total_tokens'], totals['recent_keep']['known_total_tokens']], '４課題の全入力＋全出力の合計')]:
        s += text(x, 28, heading, 27, bold=True)
        s += text(x, 63, note, 18, MUTED)
        for i, (v, label, color) in enumerate(zip(values, ['A 全履歴＋保持', 'B 直近＋保持'], [MUTED, TEAL])):
            y = 120+i*110
            s += text(x, y, label, 22, color)
            bar = (width-120)*v/max(values)
            s += f'<rect x="{x}" y="{y+18}" width="{bar:.2f}" height="27" rx="3" fill="{color}"/>'
            s += text(x+bar+15, y+41, f'{v:,}', 23, color, bold=True)
    delta = (totals['recent_keep']['known_total_tokens']/totals['full_keep']['known_total_tokens']-1)*100
    s += text(15, 340, '最初の入力は約半分', 26, TEAL, bold=True)
    s += text(610, 340, f'継続全体では {delta:.1f}% 増加', 26, RUST, bold=True)
    return svg(s, '入力の短縮と後続全体のトークン費用の違い。左右は別スケール', 365)


def orchestration_costs():
    s=text(15, 27, '費用が積み上がる経路の例（研究する問題の模式図）', 23, MUTED)
    for i,(title,sub,excess) in enumerate([
        ('情報取得','検索・API','同じ結果を再取得'),
        ('情報共有','履歴・担当間通信','不要な情報も入力'),
        ('AI呼び出し','判断・担当への依頼','同じ判断を反復'),
        ('実行','計算・操作','済んだ処理を再実行'),
        ('検証・停止','確認・修正','不要な追加確認'),
    ]):
        x=110+225*i
        s+=f'<circle cx="{x}" cy="118" r="40" fill="#e0ebe5"/>'
        s+=text(x,127,str(i+1),28,TEAL,'middle',True)
        s+=text(x,196,title,25,INK,'middle',True)
        s+=text(x,235,sub,20,MUTED,'middle')
        s+=text(x,295,excess,21,RUST,'middle')
        if i<4:s+=arrow(x+48,118,x+177,118)
    s+=text(15,352,'減らしたいのは、成果に必要な処理を除いた余分な費用。必要性の判定が研究課題。',22,bold=True)
    return svg(s,'取得・共有・AI呼び出し・実行・検証で生じ得る余分な費用',380)


def quality_cost_target():
    s=text(15,25,'目標を表す概念図・実測ではない',21,MUTED)
    s+='<path d="M140 310 H1050 M140 310 V60" fill="none" stroke="#596c79" stroke-width="2"/>'
    s+=text(20,99,'性能',24,bold=True)
    s+=text(20,132,'高い',19,MUTED)
    s+=text(670,352,'仕事全体の費用 →',24,bold=True)
    s+='<line x1="150" y1="133" x2="1045" y2="133" stroke="#91a0aa" stroke-width="2" stroke-dasharray="7 7"/>'
    s+='<circle cx="910" cy="133" r="12" fill="#596c79"/>'
    s+=text(910,102,'基準方式',24,MUTED,'middle',True)
    s+='<circle cx="400" cy="133" r="14" fill="#167a78"/>'
    s+=text(400,102,'目指す位置',25,TEAL,'middle',True)
    s+=arrow(873,133,435,133)
    s+=text(655,182,'性能を保ちながら費用を減らす',24,TEAL,'middle',True)
    s+=text(205,250,'性能：要求を満たす完了率・成果物の正しさ',22)
    s+=text(205,287,'費用：全AIトークンを主指標、操作回数・時間も記録',22)
    return svg(s,'品質を保って総費用を下げる研究目標。実測値を示すグラフではない',380)


def build_story_slides(handoff, diagnostics, later_handoff=None):
    if not handoff or not diagnostics or not diagnostics.get('all_sixteen_reviewed'):
        raise ValueError('The revised narrative requires the complete audited P31 cohort and diagnostics')
    slides = []
    def add(label, title, body, notes, refs=(), takeaway=None, cover=False):
        slides.append(dict(section=label, title=title, body=body, notes=notes, refs=refs,
                           dark=cover, cover=cover, takeaway=takeaway))
    def diagram(content):
        return '<div class="diagram story-diagram">'+content+'</div>'
    p31 = [('実験仕様', LINK+'docs/experiments/P31_handoff_factors.md')]
    results = [('全16実行の結果', LINK+'reports/P31_comparison.json'), ('結果の解釈', LINK+'docs/P31_findings.md')]
    objective=[('ユーザーと確認した研究目的',LINK+'docs/research_objective_20261022.md')]
    add('', 'AIオーケストレーションにおける<br>性能維持と実行コスト削減のための<br>ハーネス制御', '',
        '性能を維持しながら情報処理・実行の総費用を減らすという主目的を表す進捗報告の題目です。性能維持や費用削減を達成済みという意味ではありません。表紙は題名のみです。', cover=True)
    add('背景と問題：性能と費用', '性能向上に役立つ処理にも、費用がかかる',
        '<p class="lead">AIの能力と分担を活用して、複雑な仕事を任せたい。<br>取得・共有・実行・検証を増やす過程で、重複や不要な処理も生じ得る。</p>'+diagram(orchestration_costs()),
        'ここは研究の背景です。すべてのオーケストレーションが性能と費用を必ず増やすという一般的な実測主張ではありません。調査や検証が多いだけで無駄と決めず、必要な処理と避けられる処理を区別することが課題です。現状の比較では複数担当間の重複調査は未測定です。',objective)
    add('研究目的', '性能を維持し、仕事全体の実行費用を減らす',
        '<p class="lead"><strong>ハーネスが必要な情報と処理を残し、不要な取得・共有・実行を削減する。</strong></p>'+diagram(quality_cost_target()),
        'ここで性能は最終タスクの品質です。モデル自体を弱くして費用を減らすことが主題ではありません。品質維持を制約として総費用を最小化します。図は目標であり達成結果ではありません。履歴保持、結果再利用、担当再編、停止制御は目的を達成する手段の候補です。',objective)
    add('評価方針：何をもって改善とするか', '性能を保てたかを確認してから、削減量を比べる',
        '<table class="story-table"><thead><tr><th>評価すること</th><th>確認する内容</th></tr></thead><tbody>'
        '<tr><td>タスクの性能</td><td>完了率・成果物の正しさを、同じ課題の強い基準と比較</td></tr>'
        '<tr><td>総費用</td><td>取得・共有・制御・検証・失敗を含む、全入力＋全出力</td></tr>'
        '<tr><td>削減の副作用</td><td>必要情報の欠落、再取得・再実行の増加、品質低下</td></tr>'
        '<tr><td>維持と言える範囲</td><td>許容差と評価手順を事前に定め、ばらつきも確認</td></tr></tbody></table>'
        '<p class="body"><strong>一回の入力や呼び出し回数が減っても、仕事全体が高くつけば削減ではない。</strong></p>',
        '数式ではmin E[C_total(H)] subject to Q(H) >= Q(H_ref)-deltaです。deltaは結果を見て品質低下を許容するために選びません。現在の４課題各１回では、品質が維持されたという統計的な証明はできません。API回数と時間は別の単位として記録し、無根拠にトークンへ加算しません。キャッシュによる実際の計算費用も区別します。',objective,
        takeaway='現在の実験は、費用を減らすつもりの操作が逆効果になる条件を調べる段階。')
    add('現在の検証に使う仕事', '複数工程の仕事で、削減の影響を測る',
        '<p class="lead">たとえば写真整理では、方法を答えるだけでなく、<br>対象を調べて移動し、要求どおりに終えたか確かめる必要がある。</p>'+diagram(photo_workflow()),
        '社会背景は、AIへ一問一答だけでなく、複数工程を含む仕事を委ねたいという要求です。写真整理は今回の実験に含む仕事を簡略化した説明です。市場規模や導入率は主張しません。企業業務やリポジトリ変更にも複数工程はありますが、今回そこまで検証したとは述べません。',
        [('複数アプリの仕事を評価するAppWorld', 'https://arxiv.org/abs/2407.18901')])
    add('問題：途中からの継続', '作業が進むほど、引き継ぐ情報も増える',
        '<p class="lead">過去の応答や取得結果を毎回入力すると、入力が長くなる。<br>一部を省けば、作業の続きに必要な情報まで見えなくなる可能性がある。</p>'+diagram(missing_context()),
        '上限に達する場合、入力を短くする場合、担当を替える場合などに引き継ぎが必要になります。図の発言は説明用で、モデルの実際の発言ではありません。今回の課題が自然に入力上限へ達したという意味でもありません。情報が少ないと必ず失敗するという結論ではなく、どこまで省けるかが研究課題です。',
        [('文脈圧縮と費用の近接研究', 'https://arxiv.org/abs/2608.16370')])
    add('技術背景：何を引き継ぐのか', 'AIの作業状態は、三つの場所に分かれる',
        '<p class="lead">「履歴が残る」「変数が残る」「操作の結果が残る」は、それぞれ違う。</p>'+diagram(three_states()),
        '会話履歴はモデルへ渡すメッセージ、変数はPython実行環境内の値、アプリ状態はファイルや模擬アプリのDBです。例の変数名や内容は具体的な実験前半に必ず存在したという主張ではありません。初期化条件でも環境を元に戻さないことが、この比較の重要な前提です。', p31)
    add('今回の検証課題', '変数を残せば、会話履歴は減らせるか',
        '<div class="two"><div class="col"><h3>期待する利点</h3><p class="body">取得・計算した値を再利用すれば、長い過去の会話を毎回渡す費用を減らせるかもしれない。</p></div>'
        '<div class="col"><h3>確かめる必要がある点</h3><p class="body">値だけでは、その用途、未完了の作業、使うAPIが伝わらず、調べ直しが増えるかもしれない。</p></div></div>',
        '目的は、仕事の継続に必要な情報を特定し、成功を保ちながら入力と再取得の総費用を減らせる構成を明らかにすることです。どちらの仮説が成立するかを先に決めません。変数の保持自体は先行研究にあります。', p31,
        takeaway='全体目的との関係：入力を減らしても、性能低下や再取得で高くつかないかを測る。')
    add('実験システムの構成', 'ハーネスが、入力と作業状態を管理する',
        '<p class="lead">同じAIにPythonコードを生成させ、模擬アプリを操作する。<br>今回変更するのは、再開時に渡す会話と、Python状態の保持方法。</p>'+diagram(harness_architecture()),
        'モデルの重みは変更しません。ハーネスがモデル入力を組み、生成コードを隔離環境で実行し、その結果を次の入力へ戻します。APIはアプリを読む・変更する操作窓口です。一つのコード実行で複数APIを呼べるので、モデル呼出数とAPI数は別です。今回の主比較では作業役は一つです。',
        [('コード実行型の既存研究：CodeAct', 'https://proceedings.mlr.press/v235/wang24h.html'), *p31])
    add('研究全体と現在の実験', '入力削減が、別の費用を増やしていないか調べる',
        '<div class="two"><div class="col"><span class="badge">全体の研究対象</span><h3>情報取得・共有・呼び出し・<br>実行・検証の必要性を制御</h3><p class="body">担当再編や結果再利用も、性能を保って費用を減らすための手段。</p></div>'
        '<div class="col"><span class="badge">今、測っている一部分</span><h3>担当を固定し、<br>残す会話と変数を変える</h3><p class="body">入力を減らした結果、必要情報の再取得や失敗が増えないかを調べる。</p></div></div>',
        '全体目的を引き継ぎだけへ変更していません。今は局所比較へ絞っており、複数担当の通信・重複調査の削減、取得前の不要情報排除は未測定です。最初の担当再編案も手段の候補で、再編そのものが最終目的ではありません。資料ではこの階層が抜けていたことを訂正します。',objective,
        takeaway='未測定：複数担当間の重複調査・通信の削減、不要な情報を取得前に除く効果。')
    add('実験の前提①：何を解かせるか', '復元できる模擬アプリで、四つの仕事を行う',
        '<p class="lead">AppWorldの既知の開発課題を使用。要求を読ませ、ツールで実際に操作させる。</p>'
        '<table class="story-table"><thead><tr><th>仕事</th><th>必要な工程</th><th>最後に確認すること</th></tr></thead><tbody>'
        '<tr><td>写真整理</td><td>一覧取得 → 日付確認 → 移動</td><td>指定どおりの配置になったか</td></tr>'
        '<tr><td>共有・依頼</td><td>文書・連絡先・日付の確認 → 依頼</td><td>要求された処理を完了したか</td></tr>'
        '<tr><td>誤請求への返金</td><td>請求・履歴・対象の確認 → 返金</td><td>対象の処理が正しいか</td></tr>'
        '<tr><td>曲一覧の書出</td><td>複数の一覧取得 → 統合 → CSV作成</td><td>出力内容が要求を満たすか</td></tr></tbody></table>',
        '実企業のアカウントではなく、復元可能な模擬環境です。最終評価器が各課題の規則に基づいて成功を判定します。表は仕事の概要で、正解手順や隠し評価をモデルへ追加していません。この４件はすでに開発で使った課題なので、未経験課題に対する一般性は確認できません。',
        [('AppWorld', 'https://arxiv.org/abs/2407.18901'), ('課題の説明と選定', LINK+'docs/P18_findings.md')])
    add('実験の前提②：何をそろえるか', 'モデル・要求・アプリ状態・継続予算を固定する',
        '<table class="story-table"><thead><tr><th>そろえる条件</th><th>この比較での設定</th></tr></thead><tbody>'
        '<tr><td>AIとツール</td><td>同じMiniMax-M3量子化モデル・同じPython／API</td></tr>'
        '<tr><td>要求とアプリ状態</td><td>同じ要求、同じ地点まで操作済みの模擬環境</td></tr>'
        '<tr><td>再開後の上限</td><td>16回のAI応答・12万トークン・８分のいずれかまで</td></tr>'
        '<tr><td>API操作の上限</td><td>写真整理160回、他80回。共通の前半も数える</td></tr>'
        '<tr><td>成功の判定</td><td>終了後に別の評価器で判定。結果をAIへ戻さない</td></tr></tbody></table>',
        'トークンはモデルが読み書きするテキスト量の単位です。入力と出力を合計し、推論中断等の計上不明も隠しません。出力用の予約分を見込むため使用量が12万に到達する前に止まる場合があります。各条件１seedで、課題内の４条件は同じseed列です。操作を前半から再現する実験準備費用も別記します。', p31)
    add('実験手順：どこで分けるか', '同じ途中地点から、四条件で続きを実行する',
        '<p class="lead">最初から別々に走らせると、取得した情報も変わる。<br>そこで、４回目の応答と操作が終わった地点を共通の出発点にする。</p>'+diagram(fork_protocol()),
        '前半はP29の保存記録を使います。AI応答に対応するツール結果がそろった地点で区切り、全４課題に同じ規則を適用しました。環境の公開返却・API仕様・保存DBを照合し、変数保持は記録応答を使ったPython再生で確認しています。全メモリや未来の挙動の同一性は保証しません。',
        [('前半の一致確認', LINK+'reports/P31_prefix_checks.json'), *p31])
    add('比較条件：変えるのは二つ', '会話の量と、変数の保持を別々に変える',
        '<table class="factor-table"><thead><tr><th></th><th>会話を全部残す<br><span class="small">前半４回の応答＋ツール結果</span></th><th>会話は直近だけ<br><span class="small">最後の１回の応答＋ツール結果</span></th></tr></thead><tbody>'
        '<tr><th>Pythonの変数を残す</th><td><b>A</b> 全履歴＋保持</td><td><b>B</b> 直近＋保持</td></tr>'
        '<tr><th>Pythonを一度初期化</th><td><b>C</b> 全履歴＋初期化</td><td><b>D</b> 直近＋初期化</td></tr></tbody></table>'
        '<p class="body">最初の要求は全条件で残す。アプリは同じ状態。<br>過去の取得記録は、全条件でツールから再読できる。</p>',
        '直近条件は一度だけ前半の履歴を削り、その後の新しい会話はすべて追加します。初期化も引き継ぎ時の一度だけで、再開後の変数は保持します。保持か初期化かをAIへ正確に通知します。これらの通知差も介入の一部です。全履歴でも長い観測は共通の表示規則に従い、無制限に生データ全文を渡す意味ではありません。', p31)
    add('なぜ四条件が必要か', '一つずつ変えないと、何が効いたか分からない',
        '<div class="two"><div class="col"><h3>A と B を比較</h3><p class="body">変数を残したまま、会話だけ減らす。<br><strong>保持した値があれば、履歴を減らしても継続できるか。</strong></p><p class="small muted subtle">C と D も比較し、初期化した場合との違いを見る。</p></div>'
        '<div class="col"><h3>A と C を比較</h3><p class="body">同じ会話の量で、変数の保持だけ変える。<br><strong>過去の会話があっても、値を残す追加価値があるか。</strong></p><p class="small muted subtle">B と D も比較し、会話が少ない場合との違いを見る。</p></div></div>',
        '履歴短縮と変数初期化を同時に変えたA対Dだけでは、成績差をどちらで説明すべきか分かりません。この交差比較は一般的な実験法で、それ自体を新規性にはしません。主指標は予算内の最終成功、補助指標は全トークン、API操作、再取得、停止理由です。', p31,
        takeaway='評価：予算内に仕事を終えたか ＋ 最後までに使った入力・出力と操作の量。')
    task_names = ['写真整理', '共有・依頼', '返金', '曲一覧の書出']
    task_ids = list(dict.fromkeys(r['task_id'] for r in handoff['rows']))
    cells = {(r['task_id'], r['arm']): r for r in handoff['rows']}
    table = '<table class="story-table results-table"><thead><tr><th>課題</th>'+''.join(f'<th>{n.replace(" ", "<br>", 1)}</th>' for n in NAMES)+'</tr></thead><tbody>'
    for task, name in zip(task_ids, task_names):
        table += '<tr><td>'+name+'</td>'+''.join('<td class="'+('ok' if cells[task,a]['success'] else 'miss')+'">'+('○ 成功' if cells[task,a]['success'] else '— 未達')+'</td>' for a in ARMS)+'</tr>'
    table += '<tr><td><strong>成功した課題数</strong></td>'+''.join(f'<td><strong>{handoff["totals"][a]["successes"]} / 4</strong></td>' for a in ARMS)+'</tr></tbody></table>'
    add('結果①：全課題の成否', '変数を残しても、会話短縮を補えなかった',
        '<p class="lead">A と B では、同じ変数を保持している。変えたのは再開時の会話の量。</p>'+table,
        '全16分岐を示しています。Aの成功２件がBでは未達でした。一方、初期化したCとDはともに返金だけ成功です。４件各１回なので、成功率の一般的な差や統計的に確かな交互作用は主張できません。未達は要求未達であり、すべてが幻覚や情報欠落という意味ではありません。', results,
        takeaway='今回の４課題・この予算では、「変数を残すから会話を減らせる」とは言えない。')
    add('結果②：費用', '入力を短くしても、総費用は増えた',
        '<p class="lead">A と B の比較。直近だけにすると最初の入力は短くなるが、継続全体では逆転した。</p>'+diagram(cost_chart(handoff, diagnostics))+
        '<p class="small muted">単位：トークン。左右は別の尺度。実行準備の再生費用は別記。</p>',
        '左は各課題の再開直後１回だけの入力トークンの合計、右は再開後に終了するまでの全入力と全出力の合計で、左右の軸は別です。どちらも４課題合計。AとBには使用量不明の呼出しはありません。CとDには各１件の使用量不明があり、全条件の費用表は補足に残します。総費用には失敗した実行も含みます。',
        [('入力と再取得の集計', LINK+'reports/P31_program_diagnostics.json'), *results])
    matching = {a: sum(r['requests_matching_prefix'] for r in diagnostics['rows'] if r['arm'] == a) for a in ARMS}
    add('考察：何が起きたか', '短い履歴では、過去の情報を取り直す動きがあった',
        '<div class="two"><div class="col"><span class="badge">観測できたこと</span><h3>前半と同じAPI要求</h3>'
        f'<p class="body">A 全履歴＋保持：<strong>{matching["full_keep"]}回</strong><br>B 直近＋保持：<strong>{matching["recent_keep"]}回</strong></p>'
        '<p class="small">BではAPI説明・接続情報の再取得が中心。<br>４課題の継続部分を合計。</p></div>'
        '<div class="col"><span class="badge warn">次に確かめる仮説</span><h3>値と、値を使うための情報が<br>結びついていない可能性</h3><p class="body">残る変数、利用できるAPI、次の作業を示すと、再取得と未達を減らせるか。</p></div></div>',
        '同じAPI名とJSON引数が前半にあった要求を数えます。応答の変化や確認の必要性があるため、すべて無駄とは扱いません。返金のBでは、公開API仕様が未ロードの操作を要求したエラーもありました。これだけを全未達の原因とはしません。変数一覧やAPI通知は既存技術なので、普通の対照として追加する必要があります。',
        [('集計の定義と全件診断', LINK+'reports/P31_program_diagnostics.json')],
        takeaway='観測と仮説を分ける。現段階では、失敗原因も解決策の有効性も確定していない。')
    add('既存との差分と新規性', '必要な処理を残して、何を省けるかを判断する',
        '<table class="story-table"><thead><tr><th>既存の道具・方式</th><th>研究で確かめる追加価値</th></tr></thead><tbody>'
        '<tr><td>履歴圧縮・選択</td><td>省いた情報の再取得まで含め、総費用を下げられるか</td></tr>'
        '<tr><td>コード実行・状態保持・通知</td><td>既存の再利用でも残る、余分な取得・実行を減らせるか</td></tr>'
        '<tr><td>分担・検証・停止の制御</td><td>必要な調査や確認を維持したまま、重複を避けられるか</td></tr></tbody></table>'
        '<p class="body"><strong>狙う差分：</strong>不要な処理が生じる条件と、それを回避する具体的な判断規則。<br><strong>現状：</strong>独自方式と改善効果は未確立。目的を見送る判断はしていない。</p>',
        '品質を保った費用削減は目的で、それだけを新規性とはしません。一般的な道具が既存でも、具体的な状態観測、判断規則、成立条件、追加費用込みの効果に研究上の差が残る可能性はあります。近接方式を十分に強い比較相手として扱い、同等なら優位を主張しません。表の全部を今月実装するという計画ではなく、具体的な一つの削減対象へ絞ります。',
        [('CodeAct', 'https://proceedings.mlr.press/v235/wang24h.html'), ('近接研究の照合', LINK+'docs/runtime_state_overlap_20261022.md'), *objective])
    add('次の実験と判断', '削減対象を一つ決め、性能維持と総費用を比べる',
        '<div class="three"><div class="col"><div class="n">1</div><h3>費用の発生箇所を分析</h3><p class="body">入力の再利用、再取得、呼び出し・実行の反復を分ける。</p><span class="badge">'+('４・８応答後とも全件終了' if later_handoff else '８応答後は実行中')+'</span></div>'
        '<div class="col"><div class="n">2</div><h3>省く判断を固定する</h3><p class="body">必要な処理を残せる根拠と、通常方式との差を明記する。</p><span class="badge wait">対象・規則は未確定</span></div>'
        '<div class="col"><div class="n">3</div><h3>未調整課題で確認</h3><p class="body">品質の許容差を先に決め、制御費用込みの削減を測る。</p><span class="badge wait">未実施</span></div></div>',
        'P32は元の４課題の８応答後を比較し、全16件終了しました。P31と同じ課題で、時点間はseed列も異なるため純粋な時期の効果ではありません。変数一覧やAPI通知は通常の対照候補ですが、それを次の主題と自動決定しません。どの費用を減らすためか、必要な処理を落とさないかを先に定義します。',
        [('８応答後の事前仕様', LINK+'docs/experiments/P32_later_handoff.md'), ('進捗記録', 'https://github.com/sophiria1225/AI-/issues/150'), *objective],
        takeaway='新しい実験には「削減する費用・守る性能・既存の対照・採否基準」を対応させる。')
    add('現状と限界', '費用削減の落とし穴は見えた。改善方式はこれから',
        '<div class="two"><div class="col"><h3>ここまでの成果</h3><p class="body">同じ途中状態から比較できる基盤。<br>入力短縮と総費用が逆転した事例。<br>再取得の発生を追える実行記録。</p></div>'
        '<div class="col"><h3>まだ不足する証拠</h3><p class="body">性能を維持した総費用の削減。<br>既存方式に対する独自規則の追加価値。<br>未調整課題・複数担当への適用。</p></div></div>',
        '４既知課題、１モデル、各条件各境界１試行の探索です。同じ課題を別境界で試しても独立課題数を増やしません。一般的な品質維持や費用削減を達成したという意味ではありません。未閲覧の12シナリオは方式・比較を固定してから使います。',results,
        takeaway='研究の主目的は、ハーネスの情報・実行制御で、性能を保ちながら総費用を減らすこと。')
    add('月末投稿までの進め方', '10月23日に、論文の主張と主要結果を絞る',
        '<div class="timeline"><div><div class="date">10/23</div><h3>主要結果・あらまし</h3><p class="small">追加比較を閉じ、既存との差を一つに絞る。</p></div>'
        '<div><div class="date">10/25</div><h3>確認実験を終了</h3><p class="small">不足する対照と未調整課題の確認を優先する。</p></div>'
        '<div><div class="date">10/29–30</div><h3>４ページ原稿</h3><p class="small">本文・図・引用・公式様式・著者情報を確認する。</p></div>'
        '<div><div class="date">10/31</div><h3>投稿完了が目標</h3><p class="small">新規性と追加結果の成立が、現在の日程上の制約。</p></div></div>',
        '新規性の成立と未調整課題の結果は未確定で、投稿に間に合うことを保証できる状況ではありません。採録は査読に依存します。実験を延々と増やすのではなく、10月23日に中心となる主張を判断し、25日以降はその裏付けに限定して原稿を完成させます。公式４ページ組版と著者情報も未完了です。',
        [('原稿の状態', LINK+'papers/202610_letter/current_status.json')],
        takeaway='今優先すること：説明可能な一つの結果と、既存方式に対する追加価値を固める。')
    figures = {'orchestration_costs':orchestration_costs(),'quality_cost_target':quality_cost_target(),
               'task_workflow': photo_workflow(), 'handoff_problem': missing_context(), 'three_states': three_states(),
               'experiment_architecture': harness_architecture(), 'fork_protocol': fork_protocol(),
               'input_vs_total_cost': cost_chart(handoff, diagnostics)}
    return slides, figures
