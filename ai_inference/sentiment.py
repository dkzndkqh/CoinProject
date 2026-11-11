import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from config import settings

# FinBERT가 한 번에 처리하는 최대 글자 조각(토큰) 수. 모델이 허용하는 최대는 512다.
# 제목+요약은 대부분 이보다 짧지만, 긴 글이 오면 뒤를 잘라서 에러를 막는다.
MAX_TOKENS = 512

# GPU에 한 번에 올리는 기사 수. 8GB GPU에서 FinBERT는 가벼워서 넉넉하다.
BATCH_SIZE = 16


def load_model():
    tokenizer = AutoTokenizer.from_pretrained(settings.sentiment_model)
    model = AutoModelForSequenceClassification.from_pretrained(settings.sentiment_model)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()  # 추론모드
    return tokenizer, model


def to_result(probs: dict[str, float]) -> dict:
    """확률 세 개를 label과 score로 줄인다. 모델을 쓰지 않는 순수 계산이라 테스트하기 쉽다.
    probs 예: {"positive": 0.80, "negative": 0.05, "neutral": 0.15}
    - label: 확률이 가장 큰 쪽의 이름
    - score: 긍정 확률 - 부정 확률 (-1 ~ +1). 중립 확률은 점수에 직접 들어가지 않는다.
    """
    label = max(probs, key=probs.get)
    score = probs["positive"] - probs["negative"]
    return {"label": label, "score": round(score, 4)}


def analyze(tokenizer, model, texts: list[str]) -> list[dict]:
    """글 목록을 분석해 같은 순서의 결과 목록 [{"label", "score"}, ...]을 돌려준다.
    기사가 많아도 BATCH_SIZE개씩 나눠서 GPU에 올린다 (한꺼번에 올리면 메모리가 모자랄 수 있다).
    """
    results = []
    device = model.device
    id2label = model.config.id2label

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]

        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=MAX_TOKENS,
            return_tensors="pt",
        ).to(device)

        # no_grad: 학습용 계산 기록을 안 남겨서 메모리를 아낀다 (추론에는 필요 없다).
        with torch.no_grad():
            logits = model(
                **inputs
            ).logits  # 모델의 원본 출력 (아직 확률이 아닌점수 3개)

        # softmax: 점수 3개를 합이 1인 확률 3개로 바꾼다.
        probs = torch.softmax(logits, dim=-1).cpu().tolist()

        for row in probs:
            # row = [0.80, 0.05, 0.15] 를 이름과 묶는다. id2label[i].lower(): 이름을 소문자로 통일
            named = {id2label[i].lower(): p for i, p in enumerate(row)}
            results.append(to_result(named))
    return results
