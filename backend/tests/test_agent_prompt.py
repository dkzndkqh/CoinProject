from app.agent import service as agent_service

# 프롬프트는 글이라 내용 전체를 검사할 수는 없다.
# 여기서는 "카드 방식으로 바꾼 규칙"이 빠지거나 옛 지시가 되살아나는 것만 막는다.
PROMPT = agent_service._load_system_prompt()


def test_시나리오_가격을_글에_쓰라는_옛_지시가_남아있지_않다():
    assert "시나리오 상단·중앙·하단" not in PROMPT
    assert "상단(낙관)" not in PROMPT
    assert "읽기 쉽게 적어도 되지만" not in PROMPT


def test_가격은_글에_쓰지_말고_카드가_보여준다고_적혀_있다():
    assert "가격(원) 숫자를 쓰지 않는다" in PROMPT
    assert "카드" in PROMPT


def test_예측_입력_선택_기준이_코드의_경계와_같다():
    # 코드는 48시간(2일) 이상이면 일봉 입력을 쓴다. 프롬프트의 "2일"과 어긋나면 글과 카드가 다른 예측을 말한다.
    assert agent_service.DAILY_INPUT_FROM_HOURS == 48
    assert "2일 미만이면 4h 입력, 2일 이상이면 1d 입력" in PROMPT


def test_같은_문장이_연달아_두_번_들어가지_않았다():
    # 4줄에 같은 문장이 중복돼 있던 적이 있어서 확인한다.
    sentence = "사용자는 가격 전망과 시장 분석을 묻는다."
    assert PROMPT.count(sentence) == 1
