# today_candle

일봉 차트 신호 브리핑을 PDF로 만듭니다. 일봉은 FinanceDataReader(네이버 금융, 수정주가)로 받습니다.

## 실행

```
pip install -r requirements.txt
python3 -m briefing.run --charts out/charts
python3 -m briefing.news --code 373220 --out out/373220_news.json
python3 -m briefing.pdf --report out/charts/373220_report.json --news out/373220_news.json --out-dir out/reports
```

- `--code 종목코드`로 다른 종목을 볼 수 있습니다. 종목명은 `briefing/run.py`의 `NAMES`에 추가합니다.
- 뉴스는 `briefing.news`가 Google 뉴스 RSS에서 최근 3일 기사 제목을 모읍니다(본문은 열지 않음, 시세 자동 기사 제외). `--news`를 빼면 PDF에 "뉴스는 확인하지 못했습니다"로 나옵니다.
- PDF는 Chrome(Mac) 또는 Chromium(`/opt/pw-browsers`)으로 만듭니다. 다른 경로는 `BRIEFING_CHROME` 환경변수로 지정합니다.
- 클라우드에서 실행하려면 네트워크 허용 목록에 `fchart.stock.naver.com`(일봉)과 `news.google.com`(뉴스)이 있어야 합니다. 뉴스 사이트에 접속하지 못하면 오류 내용을 뉴스 칸에 적고 PDF는 그대로 만듭니다.

## 예약 실행

```
python3 -m briefing.scheduled --code 373220 --out-dir out
```

일봉 계산, 뉴스 수집, PDF 생성을 한 번에 합니다. 주말과 한국거래소 휴장일에는 `SKIP:`만 출력하고 끝냅니다. 달력에 없는 임시 휴장일(선거일 등)은 10시 이후 오늘 일봉이 없으면 휴장일로 봅니다.

## 구성

| 파일 | 하는 일 |
| --- | --- |
| `briefing/chart.py` | 일봉 조회 (FinanceDataReader) |
| `briefing/signals.py` | 이동평균, 이격도, 이평선 간격, 낙폭과대, 긴꼬리, 거래량, 최근 신호 판정 |
| `briefing/channel.py` | 중기·중기 큰 추세·단기 추세선 |
| `briefing/render.py` | 이격도 이미지와 240일 일봉 차트(SVG) |
| `briefing/run.py` | 보고서 계산과 JSON 저장 |
| `briefing/news.py` | 뉴스 수집 (Google 뉴스 RSS) |
| `briefing/pdf.py` | PDF 생성 |
| `briefing/scheduled.py` | 예약 실행 (휴장일 건너뜀) |
| `briefing/retail_candle/` | 삼성전자 개인 대량 순매수 캔들 차트. 투자자별 매매 데이터를 키움 API(`kiwoom` 패키지, 등록 IP)로 받으므로 키움 환경에서만 실행됩니다. |
