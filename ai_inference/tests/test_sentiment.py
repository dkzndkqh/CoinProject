from types import SimpleNamespace

import pytest

import sentiment

# ---- to_result: 확률 세 개 -> label, score (모델 없이 계산만 검사) ----


def test_확률이_가장_큰_쪽이_label이다():
    result = sentiment.to_result({"positive": 0.8, "negative": 0.05, "neutral": 0.15})
    assert result["label"] == "positive"


def test_score는_긍정_확률에서_부정_확률을_뺀_값이다():
    result = sentiment.to_result({"positive": 0.8, "negative": 0.05, "neutral": 0.15})
    assert result["score"] == pytest.approx(0.75)


def test_부정이_크면_score는_음수다():
    result = sentiment.to_result({"positive": 0.1, "negative": 0.7, "neutral": 0.2})
    assert (result["label"], result["score"]) == ("negative", -0.6)


def test_중립이_가장_크면_label은_neutral이고_score는_0에_가깝다():
    result = sentiment.to_result({"positive": 0.1, "negative": 0.1, "neutral": 0.8})
    assert (result["label"], result["score"]) == ("neutral", 0.0)


def test_label과_score가_엇갈릴_수_있다():
    # 중립이 1등이어도 긍정이 부정보다 크면 score는 양수다 (두 값은 독립적으로 정해진다)
    result = sentiment.to_result({"positive": 0.3, "negative": 0.1, "neutral": 0.6})
    assert result["label"] == "neutral"
    assert result["score"] == pytest.approx(0.2)


def test_score는_소수_넷째_자리까지_반올림한다():
    result = sentiment.to_result(
        {"positive": 0.123456, "negative": 0.0, "neutral": 0.876544}
    )
    assert result["score"] == 0.1235


@pytest.mark.parametrize(
    "probs, expected",
    [
        ({"positive": 1.0, "negative": 0.0, "neutral": 0.0}, 1.0),
        ({"positive": 0.0, "negative": 1.0, "neutral": 0.0}, -1.0),
    ],
)
def test_score_범위_끝값(probs, expected):
    # 백엔드는 -1~+1 밖의 score를 422로 거절하므로 끝값이 범위를 넘지 않아야 한다
    assert sentiment.to_result(probs)["score"] == expected


# ---- analyze: 가짜 모델로 순서·배치·이름 매핑을 검사 ----


class FakeTokenizer:
    """texts를 받으면 글 길이를 담은 가짜 입력을 돌려준다. .to()는 자기 자신."""

    def __call__(self, batch, **kwargs):
        self.last_kwargs = kwargs
        return FakeInputs(batch)


class FakeInputs(dict):
    def __init__(self, batch):
        super().__init__(texts=batch)

    def to(self, device):
        return self


class FakeModel:
    """글에 'good'이 있으면 positive, 'bad'가 있으면 negative, 아니면 neutral로 답한다.
    출력 순서를 일부러 FinBERT 실제 순서(positive, negative, neutral)와 다르게 둬서,
    코드가 순서를 박지 않고 id2label을 읽는지 확인한다."""

    device = "cpu"

    def __init__(self):
        self.batch_sizes = []
        # 대문자도 섞는다
        self.config = SimpleNamespace(
            id2label={0: "Neutral", 1: "Positive", 2: "Negative"}
        )

    def __call__(self, texts):
        import torch

        self.batch_sizes.append(len(texts))
        rows = []
        for t in texts:
            if "good" in t:
                rows.append([0.0, 5.0, 0.0])
            elif "bad" in t:
                rows.append([0.0, 0.0, 5.0])
            else:
                rows.append([5.0, 0.0, 0.0])

        class Out:
            logits = torch.tensor(rows)

        return Out()


def test_analyze는_입력_순서대로_결과를_돌려준다():
    model = FakeModel()
    results = sentiment.analyze(
        FakeTokenizer(), model, ["good news", "bad news", "plain news"]
    )
    assert [r["label"] for r in results] == ["positive", "negative", "neutral"]
    assert results[0]["score"] > 0 > results[1]["score"]


def test_analyze는_모델의_id2label로_이름을_붙인다():
    # 0번이 Neutral인 모델이어도 이름이 어긋나지 않는다
    (result,) = sentiment.analyze(FakeTokenizer(), FakeModel(), ["good"])
    assert result["label"] == "positive"


def test_analyze는_BATCH_SIZE개씩_나눠서_모델을_부른다():
    model = FakeModel()
    n = sentiment.BATCH_SIZE * 2 + 3
    results = sentiment.analyze(FakeTokenizer(), model, ["good"] * n)
    assert len(results) == n
    assert model.batch_sizes == [sentiment.BATCH_SIZE, sentiment.BATCH_SIZE, 3]


def test_빈_목록이면_모델을_부르지_않는다():
    model = FakeModel()
    assert sentiment.analyze(FakeTokenizer(), model, []) == []
    assert model.batch_sizes == []


def test_긴_글은_잘라서_넣도록_토크나이저에_요청한다():
    tokenizer = FakeTokenizer()
    sentiment.analyze(tokenizer, FakeModel(), ["good"])
    assert tokenizer.last_kwargs["truncation"] is True
    assert tokenizer.last_kwargs["max_length"] == sentiment.MAX_TOKENS
