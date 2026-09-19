# CLAUDE.md — Passive Video PAD + Domain Adaptation Research Harness

> **이 파일의 목적**
>
> 이 문서는 Claude Code가 이 프로젝트를 처음 접했을 때도 사용자의 업무 배경, 현재 연구 상태, 연구 가설, 데이터셋, 논문 흐름, 실험 원칙, 보안 관점의 평가 기준, 하네스 엔지니어링 구조, 코드 작성 규칙, 다음 작업 우선순위를 한 번에 이해하도록 하는 **프로젝트 최상위 운영 문서**다.
>
> 단순 README가 아니다. Claude Code가 이 저장소에서 연구·구현·실험·분석을 수행할 때 따라야 하는 **연구 헌법(research contract)** 으로 사용한다.
>
> 이 문서를 수정할 때는 연구 방향 또는 운영 규칙의 변경으로 간주한다. 사소한 코드 변경 때문에 임의로 내용을 바꾸지 않는다.

---

# 0. TL;DR — 프로젝트를 2분 안에 이해하기

이 프로젝트의 최종 목표는 **안면인식 시스템에 적용할 Passive Face Presentation Attack Detection(PAD)** 기술을 연구하고 구현하는 것이다.

현재 핵심 방향은 다음과 같다.

```text
RGB Video Input
      ↓
Passive Video PAD
(사용자에게 큰 동작을 요구하지 않음)
      ↓
Spatio-temporal Feature
      ↓
Domain Adaptation
      ↓
새 카메라 / 조명 / 거리 / 매장 환경 적응
      ↓
하지만 기존 Spoof 탐지 능력은 보존
```

특히 연구의 핵심 질문은 다음이다.

> **새로운 타깃 환경에서 쉽게 수집할 수 있는 Bona-fide(Real) 비디오만을 이용해 PAD 모델을 적응시키면서, Source에서 학습한 Spoof 공격 탐지 능력을 어떻게 보존할 것인가?**

즉 단순한 `Video PAD + DA`가 아니라 다음 문제를 연구한다.

> **Bona-fide-only Video Domain Adaptation with Spoof Knowledge Preservation for Face Anti-Spoofing**

현재 중요한 현실적 제약은 다음과 같다.

- 최종 시스템은 얼굴인식 기반 서비스 환경을 가정한다.
- RGB 카메라를 우선 연구한다.
- 향후 RGB + ToF fusion으로 확장할 계획이다.
- 사용자가 고개를 크게 돌리거나 특정 문장을 말하거나 의도적으로 눈을 깜빡이는 방식은 지양한다.
- 짧은 비디오에서 **미세한 temporal cue**를 활용하는 Passive PAD를 선호한다.
- 설치 환경은 카메라, 조명, 거리, 배경, 영상 품질 등이 다양할 수 있다.
- 최종적으로 iBeta PAD 평가를 고려하고 있으며 Level 2 수준을 목표로 검토 중이다.
- iBeta/ISO의 구체적인 최신 요구사항이나 통과 기준은 **절대로 기억에 의존하지 말고 최신 공식 자료를 다시 확인**한다.
- 기존 Domain Generalization(DG) 계열 재현 실험에서 cross-dataset 성능이 매우 낮았기 때문에 연구 중심을 Domain Adaptation(DA)으로 이동했다.
- 과거 DG 실험의 낮은 성능은 **현재 로컬 구현에서 관측한 결과**이지, 해당 논문/방법 전체가 무효라는 결론으로 일반화하지 않는다.

---

# 1. 사용자와 업무 맥락

## 1.1 역할

사용자는 AI/Vision 엔지니어이며 실제 제품과 연결되는 Face PAD 연구를 진행한다.

Claude Code는 사용자를 다음 수준으로 가정한다.

- Python / PyTorch 코드 이해 가능
- Vision 모델 학습 경험 있음
- GPU 학습 및 데이터셋 전처리 경험 있음
- 논문 구현 및 재현 실험 수행 가능
- AI 전반에 대한 이해도는 높음
- 다만 새로운 연구 분야나 논문 개념을 설명할 때는 **용어를 먼저 정의하고 직관 → 기술 설명 → 수식/코드 순서**로 설명하는 것이 좋다.

## 1.2 프로젝트가 실제 제품과 연결되는 방식

연구 대상은 일반적인 이미지 분류가 아니라 보안 시스템의 일부다.

```text
Camera
  ↓
Face Detection / Alignment
  ↓
PAD
  ├─ Bona-fide → 얼굴인식 단계 진행
  └─ Spoof → 차단
  ↓
Face Recognition
  ↓
서비스
```

따라서 단순 Accuracy 개선보다 **공격을 Real로 통과시키는 오류**가 더 중요하다.

---

# 2. 핵심 용어

## 2.1 PAD / FAS

- **PAD**: Presentation Attack Detection
- **FAS**: Face Anti-Spoofing

본 프로젝트에서는 사실상 같은 문제군을 의미하며 문헌에 따라 두 표현을 모두 사용한다.

## 2.2 Bona-fide / Real

실제 사람이 카메라 앞에 존재하는 정상 샘플.

코드와 보고서에서는 가능하면 `bona_fide`를 표준 이름으로 사용하고, 설명 문서에서는 이해를 위해 `Real`을 병기할 수 있다.

## 2.3 Spoof / Presentation Attack

예:

- Print Attack
- Replay Attack — smartphone
- Replay Attack — tablet
- Display attack
- 추후 3D mask 등

현재 우선순위는 **2D Print / Replay 공격**이다.

## 2.4 Passive PAD

사용자에게 명시적 challenge를 요구하지 않는 PAD.

피하고 싶은 UX:

```text
"고개를 왼쪽으로 돌려주세요."
"눈을 세 번 깜빡이세요."
"입을 벌려주세요."
```

선호하는 UX:

```text
사용자가 자연스럽게 카메라를 바라봄
        ↓
짧은 영상에서
texture + motion + temporal cue 분석
```

## 2.5 Domain Gap

학습 환경과 실제 배포 환경의 차이.

예:

```text
Source
- Camera A
- 30 FPS
- 밝은 실내
- 특정 codec
- 일정 거리

Target
- Camera B
- 다른 FPS
- LED 조명
- 역광
- 다른 압축
- 다른 거리
```

같은 Real 얼굴이라도 모델의 feature distribution이 달라질 수 있다.

## 2.6 DG와 DA

### Domain Generalization

Target 데이터를 학습 시점에 보지 않고 새로운 환경에서도 잘 작동하도록 만드는 접근.

```text
Source A + B + C
       ↓
Training
       ↓
Unseen Target D
```

### Domain Adaptation

Target 환경의 데이터를 일부 또는 전부 활용하여 Target 환경에 모델을 적응시킨다.

```text
Source
  ↓
Base Model
  ↓
Target data를 사용한 adaptation
  ↓
Target-specific model / classifier / prototype
```

현재 연구의 중심은 **DA**다.

## 2.7 Source-Free Domain Adaptation

Target 적응 시 원래 Source dataset을 다시 사용하지 않고 다음만 사용하는 설정.

```text
Source raw data ❌
Source-trained model ✅
Target data ✅
```

얼굴 데이터의 개인정보/보안 문제와도 잘 맞는 설정이다.

## 2.8 Real-only / Bona-fide-only Adaptation

Target에 Spoof 샘플이 거의 없고 정상 사용자 데이터만 있는 현실적 상황.

```text
Target
Real
Real
Real
Real
...
```

이 데이터를 그대로 전체 모델에 fine-tuning하면 기존 spoof knowledge가 약해질 수 있다.

---

# 3. 현재 연구 상태와 이미 내린 의사결정

## 3.1 초기 방향 — Domain Generalization

과거에는 다음과 같은 DG 계열을 검토/구현했다.

- GD-FAS
- IADG
- ResNet 기반 방법
- CLIP feature를 활용하는 방법

관측된 문제:

- cross-dataset에서 정확도가 약 50% 수준까지 떨어진 실험이 있었음
- AUC가 약 0.5 근처까지 떨어진 실험이 있었음
- 논문 표의 성능과 공개 코드/로컬 재현 성능 사이에 큰 차이를 경험함

**주의**

이 결과를 다음처럼 일반화하지 않는다.

```text
"DG는 모두 안 된다" ❌
"해당 논문은 성능을 조작했다" ❌
```

정확한 표현:

> 현재 사용한 데이터 구성, 구현, 전처리, 학습 조건에서 DG 계열 재현 성능이 기대보다 낮았으며, 실제 Target 환경 데이터를 활용할 수 있는 제품 조건을 고려해 DA를 중심으로 연구 방향을 전환했다.

## 3.2 현재 방향 — Video + DA

현재 중심 아이디어:

```text
Passive RGB Video
        ↓
Video PAD backbone
        ↓
Spatio-temporal representation
        ↓
Target adaptation
        ↓
Spoof knowledge preservation
```

## 3.3 향후 방향 — RGB + ToF

현재는 RGB를 우선한다.

ToF는 향후 다음과 같이 확장할 수 있다.

```text
RGB branch
   +
ToF / depth branch
   ↓
Feature fusion
   ↓
PAD
```

현재 MVP 하네스에서는 ToF pipeline을 강제로 넣지 않는다.
단, config schema는 향후 modality 확장이 가능하게 설계한다.

---

# 4. 가장 중요한 연구 문제

## RQ1. Video가 frame-only PAD보다 실제로 도움이 되는가?

특히 사용자가 거의 움직이지 않는 경우에도 다음 정보가 유효한지 확인한다.

- 작은 landmark movement
- local facial motion
- display flicker
- moiré 변화
- reflection 변화
- temporal compression artifact
- frame timing
- rPPG와 유사한 생체 temporal cue

## RQ2. Real-only DA가 실제로 Spoof 보안을 악화시킬 수 있는가?

가설:

```text
Target Bona-fide만 사용해 전체 모델을 fine-tuning
                     ↓
Target BPCER 개선 가능
                     +
Source spoof representation forgetting
                     ↓
일부 attack APCER 증가 가능
```

즉:

> 정상 사용자는 더 잘 통과하지만 공격도 더 잘 통과하는 **security regression**이 발생할 수 있다.

## RQ3. Spoof knowledge를 유지하면서 Target Real에 적응할 수 있는가?

검토할 방법:

1. encoder freeze
2. classifier-only adaptation
3. prototype adaptation
4. source prototype preservation
5. feature distillation
6. spoof margin preservation
7. temporal consistency constraint
8. source-model teacher constraint
9. adapter/LoRA 등 제한적 parameter update

## RQ4. Frame-level adaptation과 Clip-level adaptation 중 무엇이 더 안전하고 효과적인가?

```text
Video
 ├─ frame features → Frame DA
 └─ clip feature   → Clip DA
```

비교:

- Frame-only DA
- Clip-only DA
- Frame + Clip DA
- No DA
- Naive full fine-tuning

---

# 5. Real-only DA가 왜 위험할 수 있는지

## 5.1 Naive fine-tuning

예:

```python
prediction = model(target_bona_fide_video)
loss = real_classification_loss(prediction)
loss.backward()
optimizer.step()
```

모델이 계속 받는 메시지는 사실상:

> "이 Target 카메라에서 들어오는 패턴은 Real이다."

뿐이다.

이 과정에서 Real 영역이 과도하게 넓어지면 Spoof가 Real 영역으로 들어올 수 있다.

## 5.2 Catastrophic Forgetting

새로운 domain을 학습하면서 이전에 배운 공격 feature가 약해지는 현상.

PAD에서는 일반적인 forgetting보다 더 위험하다.

잊어버리는 대상이:

- print texture
- display artifact
- replay temporal artifact
- reflection
- moiré
- spoof-specific representation

이기 때문이다.

## 5.3 Video에서는 더 복잡하다

Target Real video는 다음을 공유한다.

- target camera sensor noise
- FPS
- codec
- compression
- exposure
- illumination flicker

하지만 Replay Attack 역시 **같은 target camera로 촬영**된다.

따라서 환경 cue 자체를 Real cue로 과도하게 학습하면 Replay에도 취약해질 수 있다.

---

# 6. 연구 데이터셋 현황

> 실제 filesystem 위치, 라이선스, 데이터 버전, subject split은 저장소를 검사한 뒤 `data/manifests/`에 기록한다.
> 여기 적힌 내용은 연구 맥락이며 실제 파일 존재 여부를 의미하지 않는다.

| Dataset | 현재 상태 | Video 여부 | 주요 용도 |
|---|---|---:|---|
| SiW-M / SiW-M v2 | 보유/사용 경험 | O | 다양한 spoof type, video |
| Replay-Attack | 보유/사용 경험 | O | replay/print, video |
| CelebA-Spoof | 보유/사용 경험 | 주로 image | cross-domain image 평가, video temporal 실험에는 직접 사용 금지 |
| AIHub 한국인 안면 이미지 | 보유/검토 | 데이터별 상이 | 한국인 domain |
| AIHub Liveness Detection 영상 | 보유/검토 | O | 한국 환경 video |
| OULU-NPU | 추가 예정/검토 | O | mobile/video PAD |
| CASIA-FASD | 추가 예정/검토 | O | standard cross-dataset |
| WMCA | 추가 예정/검토 | O / multimodal | RGB + depth/IR 확장 가능 |
| MSU-MFSD | 필요 시 | O | standard cross-dataset |

## 6.1 중요한 데이터 원칙

### CelebA-Spoof 주의

CelebA-Spoof는 video temporal model의 정상적인 clip 입력으로 간주하지 않는다.

한 image를 반복해서 가짜 sequence로 만드는 방식은:

- temporal cue를 만들지 못함
- 실제 video PAD 비교를 왜곡할 수 있음

따라서 특별한 ablation 목적이 아니라면 Video PAD의 핵심 평가에서는 제외하거나 frame baseline 용도로 사용한다.

### Subject leakage 금지

같은 사람이 train / val / test에 동시에 포함되지 않도록 dataset 공식 protocol을 우선한다.

### Adaptation/test leakage 금지

Target adaptation에 사용한 샘플은 테스트 metric 계산에서 분리하는 것을 원칙으로 한다.

논문의 공식 protocol이 다르면 정확히 기록하고 동일 protocol 안에서만 비교한다.

---

# 7. 우선 읽어야 할 핵심 논문

아래는 **이해 순서**다. 연도순이 아니다.

## 7.1 PAD 기본 개념

### 1) Learning Deep Models for Face Anti-Spoofing: Binary or Auxiliary Supervision
- CVPR 2018
- Yaojie Liu et al.
- 핵심: depth + rPPG, spatial / temporal cue의 직관
- Paper:
  https://openaccess.thecvf.com/content_cvpr_2018/html/Liu_Learning_Deep_Models_CVPR_2018_paper.html
- PDF:
  https://openaccess.thecvf.com/content_cvpr_2018/papers/Liu_Learning_Deep_Models_CVPR_2018_paper.pdf

### 2) Searching Central Difference Convolutional Networks for Face Anti-Spoofing
- CVPR 2020
- CDCN / CDCN++
- 핵심: texture / intensity / gradient 기반 spoof cue
- Paper:
  https://openaccess.thecvf.com/content_CVPR_2020/html/Yu_Searching_Central_Difference_Convolutional_Networks_for_Face_Anti-Spoofing_CVPR_2020_paper.html
- Code:
  https://github.com/ZitongYu/CDCN

## 7.2 Video PAD

### 3) Learning Multi-Granularity Temporal Characteristics for Face Anti-Spoofing
- IEEE TIFS 2022
- Temporal Transformer Network (TTN)
- 핵심:
  - Temporal Difference Attention
  - Pyramid Temporal Aggregation
  - multi-tempo temporal feature
- IEEE:
  https://ieeexplore.ieee.org/document/9730902/
- DOI:
  https://doi.org/10.1109/TIFS.2022.3158062

### 4) G²V²former: Graph Guided Video Vision Transformer for Face Anti-Spoofing
- IEEE TIFS 2025
- 핵심:
  - video
  - facial landmarks
  - photometric + dynamic feature
  - spatial / temporal attention
  - low-semantic facial motion
- DOI:
  https://doi.org/10.1109/TIFS.2025.3586506
- arXiv:
  https://arxiv.org/abs/2408.07675

**주의**
- 코드 공개 상태는 구현 시작 시점에 다시 확인한다.
- secondary blog나 임의 재구현보다 논문 원문을 우선한다.

## 7.3 DA / Source-Free DA

### 5) Source-Free Domain Adaptation with Contrastive Domain Alignment and Self-Supervised Exploration for Face Anti-Spoofing
- ECCV 2022
- 이름: SDA-FAS
- 핵심:
  - Source-free DA
  - source prototype
  - contrastive domain alignment
  - target unlabeled self-training
- Paper:
  https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/362_ECCV_2022_paper.php
- PDF:
  https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136720506.pdf
- Code:
  https://github.com/YuchenLiu98/ECCV2022-SDA-FAS

### 6) Multi-Domain Learning for Updating Face Anti-Spoofing Models
- ECCV 2022
- 핵심:
  - target 데이터로 model update
  - catastrophic forgetting
  - 기존 spoof knowledge 보존
- 현재 연구 문제와 매우 중요하게 연결됨.
- Paper:
  https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/7360_ECCV_2022_paper.php

### 7) Source-Free Domain Adaptation With Domain Generalized Pretraining for Face Anti-Spoofing
- IEEE TPAMI 2024
- SDA-FAS++
- 핵심:
  - DG-style source pretraining
  - SFDA
  - domain/identity bias 완화
- PubMed:
  https://pubmed.ncbi.nlm.nih.gov/38412088/
- DOI:
  https://doi.org/10.1109/TPAMI.2024.3370721

### 8) Category-Conditional Gradient Alignment for Domain Adaptive Face Anti-Spoofing
- IEEE TIFS 2024
- CCGA-FAS
- 핵심:
  - UDA
  - K-shot semi-supervised DA
  - teacher-student
  - pseudo category
  - category-conditional gradient alignment
- IEEE:
  https://ieeexplore.ieee.org/document/10734389/
- DOI:
  https://doi.org/10.1109/TIFS.2024.3486098

### 9) Optimal Transport-Guided Source-Free Adaptation for Face Anti-Spoofing
- CVPR 2025
- 현재 연구와 가장 직접적으로 연결되는 DA 논문 중 하나
- 핵심:
  - prototype-based adaptation
  - base model parameter를 직접 업데이트하지 않는 설정
  - few-shot target adaptation
  - training-free / lightweight adaptation
  - one-class adaptation 분석
- Paper:
  https://openaccess.thecvf.com/content/CVPR2025/html/Li_Optimal_Transport-Guided_Source-Free_Adaptation_for_Face_Anti-Spoofing_CVPR_2025_paper.html
- PDF:
  https://openaccess.thecvf.com/content/CVPR2025/papers/Li_Optimal_Transport-Guided_Source-Free_Adaptation_for_Face_Anti-Spoofing_CVPR_2025_paper.pdf

---

# 8. 논문 리서치 원칙

Claude Code 또는 Research Subagent는 논문 관련 답을 작성할 때 다음 순서를 지킨다.

```text
Search
  ↓
Primary Source 확보
  ↓
논문 PDF/official page 확인
  ↓
Method 확인
  ↓
Experiment table 확인
  ↓
Protocol 확인
  ↓
Claim DB 기록
```

## 8.1 금지

다음은 근거로 사용하지 않는다.

- 검색 결과 snippet만 보고 성능 수치 확정
- ResearchGate 요약만 보고 세부 protocol 확정
- 다른 논문의 related work 표만 보고 원 논문의 수치 확정
- 블로그가 인용한 HTER/AUC를 원 논문 확인 없이 기록
- GitHub README만 보고 논문의 최종 성능 수치 확정

## 8.2 Claim 구조

`research/claims/claims.jsonl` 예시:

```json
{
  "claim_id": "ota_2025_oneclass_001",
  "claim": "Real-only target adaptation can degrade performance in at least one evaluated cross-domain setting.",
  "paper_id": "li2025ota",
  "source_type": "primary_paper",
  "section": "experiment_one_class",
  "table": "VERIFY_FROM_PDF",
  "protocol": "VERIFY_FROM_PDF",
  "metric": "HTER",
  "value": null,
  "verified": false,
  "notes": "Do not fill exact value until checked from the primary PDF."
}
```

**수치가 검증되지 않은 상태에서는 null을 유지한다.**

---

# 9. 현재 연구에서 비교할 모델 계층

## 9.1 Frame-based baseline

최소 하나 이상의 강한 frame baseline을 유지한다.

목적:

> Video model이 정말 temporal 정보 때문에 좋아지는 것인지 확인.

후보:

- CDCN / CDCN++
- ResNet-based baseline
- 현재 보유한 GD-FAS/IADG implementation 중 재현 가능한 모델

## 9.2 Video baseline

우선순위:

1. G²V²former 재현 가능 여부 조사
2. TTN 재현 가능 여부 조사
3. 재현이 어려우면 TimeSformer / VideoMAE 계열 generic video backbone + PAD head를 baseline으로 구성
4. 단순 `frame encoder + temporal transformer` baseline을 반드시 하나 둔다.

단순 baseline 예:

```text
T frames
   ↓
Shared CNN / ViT frame encoder
   ↓
f1, f2, ..., fT
   ↓
Temporal Transformer / GRU
   ↓
Clip embedding
   ↓
Real / Spoof
```

너무 복잡한 신규 구조를 제안하기 전에 이 baseline으로 문제 자체를 증명한다.

---

# 10. DA 비교군

최소 다음 비교를 만든다.

## Baseline A — Source Only

```text
Source Real + Spoof
       ↓
Video PAD
       ↓
Target test
```

Target adaptation 없음.

## Baseline B — Naive Bona-fide-only Full Fine-tuning

```text
Source-trained model
       ↓
Target Real only
       ↓
all layers fine-tune
```

목적:

- target BPCER 개선 여부
- APCER security regression 발생 여부
- catastrophic forgetting 확인

## Baseline C — Frozen Encoder

```text
Video Encoder 🔒
     ↓
Target Real
     ↓
classifier / adapter only
```

## Baseline D — Prototype Adaptation

OTA와 유사한 철학:

```text
Base model 🔒
     ↓
Source prototypes
     ↓
Target Real distribution
     ↓
limited prototype adaptation
```

## Proposed — Spoof-Preserving Video DA

최종 연구 방향 후보:

```text
Target Real Video
        ↓
Frozen / partially frozen Video Encoder
        ↓
Target adaptation
        +
Spoof knowledge preservation
        +
Temporal consistency
        ↓
PAD
```

---

# 11. Proposed method를 바로 구현하지 말 것

아직 Proposed 구조는 **확정된 알고리즘이 아니라 연구 가설**이다.

Claude Code는 다음 순서를 반드시 따른다.

```text
1. Dataset protocol 정상화
2. Frame baseline
3. Video baseline
4. Source-only cross-domain benchmark
5. Naive real-only DA
6. 실제 security regression 존재 여부 확인
7. 그 다음 preservation method 설계
```

문제가 실제로 존재하는지 실험하지 않은 상태에서 복잡한 loss를 먼저 구현하지 않는다.

---

# 12. 가능한 Spoof Knowledge Preservation 아이디어

다음은 후보이며 모두 동시에 구현하지 않는다.

## 12.1 Frozen encoder

가장 단순한 안전장치.

```text
Video Encoder = freeze
Adaptation Head = trainable
```

## 12.2 Source prototype preservation

Source 학습 후 class / cluster prototype을 저장.

예:

```text
P_real = {r1, r2, ...}
P_spoof = {s1, s2, ...}
```

Target Real adaptation 시 `P_spoof`는 고정하거나 strong regularization을 건다.

## 12.3 Margin preservation

Target Real prototype이 Spoof prototype에 지나치게 접근하지 못하게 한다.

개념:

```text
distance(target_real, spoof_proto) >= margin
```

예시 loss:

```math
L_margin = max(0, m - d(z_target_real, P_spoof))
```

실제 구현 전에 embedding normalization과 distance metric을 검증한다.

## 12.4 Teacher preservation

Source model을 frozen teacher로 유지한다.

```text
Source Teacher 🔒
        ↓
Source-like synthetic / replayed features
        ↓
Student가 기존 판단을 너무 잃지 않도록 distillation
```

Source raw data를 쓰지 않는 설정에서는 prototype, statistics 또는 허용된 rehearsal representation을 활용한다.

## 12.5 Temporal consistency

같은 clip 내 인접 subclip에서 prediction이 과도하게 출렁이지 않게 한다.

단, **모든 temporal 변화가 작아야 한다**고 가정하지 않는다.
Spoof cue 자체가 temporal variation일 수 있으므로 consistency가 공격 정보를 지워버리지 않는지 ablation이 필요하다.

---

# 13. Loss 설계 초안

최종 수식이 아니다.

개념적 총 loss:

```math
L_total =
L_pad
+ λ_da L_domain
+ λ_preserve L_spoof_preserve
+ λ_temp L_temporal
```

각 항목은 독립 ablation을 수행한다.

```text
A. L_pad
B. L_pad + L_domain
C. L_pad + L_domain + L_spoof_preserve
D. L_pad + L_domain + L_temporal
E. Full
```

새 loss를 추가할 때마다 다음을 확인한다.

- 왜 필요한가?
- 어떤 failure mode를 줄이려는가?
- metric 중 무엇을 개선해야 하는가?
- 다른 metric을 희생하는가?
- 이 효과가 단순 regularization 때문인가?

---

# 14. 평가 지표

## 14.1 필수

### APCER
Attack Presentation Classification Error Rate

> 공격인데 Bona-fide로 통과시킨 비율.

**보안 관점 핵심 metric.**

### BPCER
Bona Fide Presentation Classification Error Rate

> 진짜 사용자인데 공격으로 차단한 비율.

UX와 관련.

### ACER

보통 APCER/BPCER의 평균 형태로 사용되나 dataset/protocol 정의를 그대로 따른다.

### HTER
Half Total Error Rate

문헌 비교용으로 사용하되 threshold 설정 방법과 protocol을 함께 기록한다.

### AUC
ROC AUC.

AUC 하나만으로 보안 성능을 결론내리지 않는다.

## 14.2 반드시 공격 유형별로 쪼개기

예:

```text
APCER_print
APCER_replay_phone
APCER_replay_tablet
APCER_replay_high_refresh
APCER_other
```

가능하면 **PAI(Presentation Attack Instrument)별 성능**을 기록한다.

## 14.3 Security Regression Gate

DA 전/후를 다음처럼 검사한다.

예:

```text
Source-only:
  BPCER = 8%
  Replay APCER = 2%

Real-only DA:
  BPCER = 2%
  Replay APCER = 15%
```

이 경우:

```text
UX improved ✅
Security regressed ❌
Overall result = SECURITY_REGRESSION
```

AUC가 높아졌더라도 security regression을 성공으로 보고하지 않는다.

---

# 15. Protocol Lock

연구에서 가장 중요한 자동화 규칙 중 하나다.

서로 다른 protocol 결과를 직접 우열 비교하지 않는다.

각 experiment에 다음을 저장한다.

```yaml
protocol:
  protocol_id: ocim_target_i_v1

  source_datasets:
    - OULU_NPU
    - CASIA_FASD
    - MSU_MFSD

  target_dataset:
    - REPLAY_ATTACK

  source_classes:
    - bona_fide
    - spoof

  target_adaptation:
    enabled: true
    supervision: bona_fide_only
    shots_per_subject: null
    total_samples: 100

  target_test:
    exclude_adaptation_samples: true

  attack_types:
    - print
    - replay

  threshold:
    source: dev_set
    policy: fixed_after_dev
```

## 15.1 Protocol Hash

비교 가능한 실험인지 자동 확인하기 위해 protocol canonical JSON으로 hash를 만든다.

예:

```text
protocol_hash = SHA256(canonical_protocol_json)
```

직접 비교:

```text
same protocol_hash → direct comparison allowed
different hash     → comparison requires explicit justification
```

단, ablation에서 의도적으로 한 요소를 변경한 경우에는 `parent_protocol_id`와 변경점을 기록한다.

---

# 16. Experiment Specification

LLM이 shell command를 임의 생성해 대규모 실험을 돌리는 방식은 지양한다.

LLM은 먼저 실험 spec을 만든다.

예:

```yaml
experiment:
  id: exp_video_da_001
  title: g2v2_source_only_replay_target
  hypothesis: >
    Video temporal modeling improves cross-domain PAD compared with the frame baseline.

model:
  family: g2v2former
  checkpoint: null
  input:
    modality: rgb
    frames: 8
    frame_sampling: uniform
    image_size: [224, 224]

data:
  source:
    - OULU_NPU
    - CASIA_FASD
  target:
    - REPLAY_ATTACK

adaptation:
  enabled: false
  method: none

training:
  seed: 42
  epochs: 50
  batch_size: 8
  learning_rate: 0.0001

evaluation:
  metrics:
    - APCER
    - BPCER
    - ACER
    - HTER
    - AUC
  per_attack_apcer: true

execution:
  smoke_test_first: true
  allow_full_gpu_run: false
  expected_gpu: H100

tracking:
  mlflow_experiment: pad-video-da
```

## 중요한 규칙

`allow_full_gpu_run: false` 상태에서는:

- 데이터 validation
- forward pass
- 1~N batch smoke test
- short dry-run

까지만 수행한다.

장시간 GPU 학습은 `true`가 된 명시적 spec에서만 실행한다.

---

# 17. 재현성 규칙

모든 run에 최소 다음을 기록한다.

- git commit SHA
- dirty working tree 여부
- experiment YAML
- dataset manifest hash
- protocol hash
- random seed
- Python version
- PyTorch version
- CUDA version
- GPU model
- driver version
- package lock hash
- checkpoint source
- model initialization
- metric threshold source
- wall-clock training time
- inference latency 측정 조건

---

# 18. Harness Engineering 방향

## 18.1 Claude Code를 중심으로 시작

이 프로젝트에서는 별도의 coding agent framework를 처음부터 추가하지 않는다.

우선 Claude Code 자체 기능을 활용한다.

```text
CLAUDE.md
   +
.claude/rules/
   +
.claude/agents/
   +
Claude Code Hooks
   +
Experiment Harness
```

Claude Code 중심 구조의 장점:

- 프로젝트 단위 instructions
- subagent
- hooks
- CLI/file/tool 사용
- MCP 확장
- worktree 기반 격리 가능

## 18.2 외부 LangGraph는 Optional

다음 조건이 생기기 전까지 필수가 아니다.

- 여러 날 이어지는 자동 research loop
- 세션 종료 후에도 graph state 복원 필요
- 별도 웹 서비스형 autonomous researcher
- 여러 worker / queue orchestration
- human-in-the-loop checkpoint를 서비스 형태로 운영

필요해지면 LangGraph를 orchestration layer로 추가한다.

---

# 19. 권장 기술 스택

| 영역 | 권장 |
|---|---|
| Interactive Agent / Coding | Claude Code |
| Project Instructions | CLAUDE.md + `.claude/rules/` |
| Isolated Research Workers | Claude Code Subagents |
| Deterministic Enforcement | Claude Code Hooks |
| Python environment | uv |
| Config | Hydra / OmegaConf |
| Experiment Tracking | MLflow |
| Dataset / large artifact versioning | DVC |
| Code versioning | Git |
| Container | Docker |
| HPC 필요 시 | Apptainer |
| Slurm 환경일 경우 | Submitit/Hydra launcher 검토 |
| Metrics | custom PAD metrics + sklearn |
| Tests | pytest |
| Lint | ruff |
| Type checks | pyright 또는 mypy |
| Tracking backend MVP | local MLflow + SQLite |
| Team/scale-up | MLflow server + PostgreSQL + object storage |

---

# 20. Hydra 사용 원칙

모델마다 Python 파일을 복사해서 실험하지 않는다.

잘못된 예:

```text
train_g2v2_8frame.py
train_g2v2_16frame.py
train_g2v2_ota.py
train_g2v2_ota_v2.py
```

올바른 방향:

```text
train.py
configs/
  model/
  dataset/
  adaptation/
  protocol/
```

예:

```bash
python train.py \
  model=g2v2former \
  model.frames=8 \
  adaptation=none \
  protocol=ocm_to_i
```

sweep:

```bash
python train.py -m \
  model.frames=4,8,16 \
  adaptation=none,prototype
```

단, 무분별한 combinatorial sweep를 만들지 않는다.

---

# 21. MLflow 사용 원칙

각 실행을 run으로 기록한다.

필수 tags:

```text
research_question
protocol_id
protocol_hash
model_family
adaptation_method
target_supervision
dataset_manifest_hash
git_sha
status
```

필수 metrics:

```text
apcer
bpcer
acer
hter
auc
```

가능하면:

```text
apcer_print
apcer_replay_phone
apcer_replay_tablet
```

Artifacts:

- resolved config
- ROC curve
- confusion matrix
- per-attack table
- training curves
- checkpoint
- environment snapshot
- evaluation JSON

---

# 22. DVC 사용 원칙

Git에 raw dataset을 직접 commit하지 않는다.

예:

```text
data/raw/
data/processed/
checkpoints/
```

대용량 데이터는 DVC tracking 또는 조직에서 허용된 artifact storage를 사용한다.

반드시 확인:

- dataset license
- 개인정보 정책
- 외부 cloud upload 가능 여부

얼굴 원본 데이터는 사용자의 명시적 승인이나 회사 정책 확인 없이 외부 저장소에 업로드하지 않는다.

---

# 23. Claude Code Subagent 설계

처음에는 **3개만** 만든다.

에이전트 수를 늘리는 것이 목표가 아니다.

## 23.1 `paper-researcher`

역할:

- 논문 검색
- primary source 확보
- PDF method/experiment 확인
- claim DB 작성
- 공개 코드 여부 확인
- protocol 추출

금지:

- 코드 수정
- GPU 학습 실행
- 검증되지 않은 수치 확정

출력 template:

```markdown
# Paper Review

## Citation
## Research Question
## Input
## Model
## Temporal Modeling
## DA Setting
## Target Data Usage
## Dataset
## Protocol
## Metrics
## Exact Table Results
## Code
## Reproducibility Risk
## Relevance to Our Research
## Verified Claims
## Unknowns
```

## 23.2 `experiment-engineer`

역할:

- repo 분석
- environment 구성
- dataset adapter
- model adapter
- experiment config
- smoke test
- unit/integration test
- MLflow logging

금지:

- protocol 임의 변경
- test set로 threshold tune
- 승인되지 않은 full GPU sweep
- raw dataset 삭제

## 23.3 `research-reviewer`

역할:

항상 비판적 reviewer 시각으로 결과를 검토한다.

질문:

```text
정말 DA 효과인가?
dataset leakage가 없는가?
same subject가 train/test에 있지 않은가?
threshold를 test에서 고른 것은 아닌가?
adaptation target이 test에 포함되었나?
protocol이 baseline과 동일한가?
APCER는 악화되지 않았나?
seed 하나만 보고 결론냈나?
전체 AUC가 좋아졌지만 특정 replay PAI가 무너진 것은 아닌가?
```

코드는 기본적으로 read-only reviewer로 시작한다.

---

# 24. Claude Code Hooks 설계

Hooks는 LLM의 자율 판단에 맡기지 않고 **항상 실행되어야 하는 규칙**에 사용한다.

## 24.1 PreToolUse — 위험한 명령 차단

차단 또는 확인 대상:

```text
rm -rf data/
rm -rf checkpoints/
git reset --hard
git clean -fd
dvc destroy
대규모 외부 업로드
```

## 24.2 PostToolUse — 코드 변경 후 검증

Python 코드 edit 후:

```text
ruff check
targeted pytest
```

모든 edit마다 전체 테스트를 돌려 작업을 느리게 하지 않는다.
변경된 영역 중심으로 실행한다.

## 24.3 Experiment launch hook

`train.py` 장시간 실행 전:

```text
experiment YAML 존재?
protocol validation 통과?
allow_full_gpu_run == true?
MLflow experiment 설정?
git state 기록?
dataset manifest 존재?
```

하나라도 실패하면 full run을 막는다.

## 24.4 Protected files

다음은 임의 변경 방지:

```text
CLAUDE.md
data/manifests/*
research/claims/*
protocol definitions
```

자동 수정은 가능하되 diff를 명확히 보여주고 research semantics가 바뀌는 수정은 사용자 검토 대상으로 남긴다.

---

# 25. 저장소 권장 구조

```text
pad-research/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .dvcignore
├── dvc.yaml
│
├── .claude/
│   ├── settings.json
│   ├── rules/
│   │   ├── research-integrity.md
│   │   ├── experiment-safety.md
│   │   ├── data-governance.md
│   │   └── coding-style.md
│   └── agents/
│       ├── paper-researcher.md
│       ├── experiment-engineer.md
│       └── research-reviewer.md
│
├── configs/
│   ├── config.yaml
│   ├── model/
│   │   ├── frame_baseline.yaml
│   │   ├── ttn.yaml
│   │   └── g2v2former.yaml
│   ├── data/
│   │   ├── replay_attack.yaml
│   │   ├── oulu_npu.yaml
│   │   └── siwm.yaml
│   ├── adaptation/
│   │   ├── none.yaml
│   │   ├── full_finetune.yaml
│   │   ├── head_only.yaml
│   │   ├── prototype.yaml
│   │   └── spoof_preserve.yaml
│   └── protocol/
│       └── ...
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── manifests/
│
├── research/
│   ├── papers/
│   │   ├── paper_index.yaml
│   │   └── reviews/
│   ├── claims/
│   │   └── claims.jsonl
│   ├── hypotheses/
│   └── decisions/
│       └── ADR-*.md
│
├── src/
│   └── pad_research/
│       ├── data/
│       ├── models/
│       │   ├── frame/
│       │   └── video/
│       ├── adaptation/
│       ├── losses/
│       ├── metrics/
│       ├── evaluation/
│       ├── tracking/
│       ├── protocols/
│       └── utils/
│
├── scripts/
│   ├── prepare_dataset.py
│   ├── train.py
│   ├── adapt.py
│   ├── evaluate.py
│   ├── validate_protocol.py
│   └── summarize_experiment.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── protocol/
│
├── experiments/
│   ├── specs/
│   └── reports/
│
└── artifacts/
    ├── figures/
    └── tables/
```

---

# 26. Architecture Decision Record(ADR)

중요한 연구/엔지니어링 결정은 `research/decisions/`에 기록한다.

예:

```text
ADR-001-use-video-input.md
ADR-002-switch-dg-to-da.md
ADR-003-real-only-target-setting.md
ADR-004-protocol-lock.md
```

Template:

```markdown
# ADR-XXX — 제목

## Status
Accepted / Proposed / Superseded

## Context

## Decision

## Alternatives Considered

## Why

## Risks

## Evidence

## Date
```

이렇게 해야 나중에 Claude가 과거에 버린 아이디어를 이유도 모르고 다시 도입하지 않는다.

---

# 27. Coding Rules

## 27.1 먼저 읽고 수정

코드를 수정하기 전에:

1. 해당 module 읽기
2. call path 확인
3. config dependency 확인
4. 테스트 확인
5. 최소 수정

## 27.2 Paper implementation

논문 재현은 다음 순서:

```text
official code 존재?
   ↓ yes
official repo baseline
   ↓
정확한 commit/tag 기록
   ↓
원 논문 설정 확인
   ↓
최소 수정으로 실행

no
   ↓
paper implementation spec 작성
   ↓
review
   ↓
implementation
```

임의로 논문 구조를 "아마 이렇겠지"라고 구현하지 않는다.

## 27.3 실험 로직과 research logic 분리

training loop 안에 특정 논문 protocol을 hard-code하지 않는다.

나쁜 예:

```python
if dataset == "replay":
    ...
```

좋은 예:

```python
protocol = load_protocol(cfg.protocol)
```

## 27.4 Metric test 필수

APCER/BPCER/HTER는 구현 실수 위험이 크므로 toy example로 unit test를 만든다.

---

# 28. Video Sampling 실험

초기 실험에서 최소 다음 비교를 고려한다.

```text
T = 1
T = 4
T = 8
T = 16
```

Sampling 후보:

- uniform
- consecutive
- random temporal crop

모든 모델이 같은 frame budget을 사용할 수 없는 경우 FLOPs/latency를 함께 기록한다.

## Low-motion protocol

연구 목적상 일반 video 성능만 보지 않고 가능하면 별도의 low-motion subset을 만든다.

예시 방법:

- landmark displacement
- optical flow magnitude
- head pose delta

중 하나를 기준으로 clip motion score를 계산한다.

그 후:

```text
Low motion
Medium motion
High motion
```

으로 나눠 Video PAD 성능을 비교하면 연구 질문과 직접 연결된다.

단, threshold는 결과를 본 뒤 임의 선택하지 말고 dev set 또는 사전 정의 규칙으로 정한다.

---

# 29. Experiment Roadmap

## Phase 0 — Harness MVP

목표:

> 연구 결과를 내기 전에 결과를 믿을 수 있는 실험 시스템을 만든다.

완료 조건:

- project scaffold
- uv
- Hydra
- MLflow local tracking
- dataset manifest schema
- protocol schema
- metrics tests
- protocol validator
- experiment spec validator
- Claude subagents
- safety hooks

## Phase 1 — Data & Evaluation Sanity

- Replay-Attack 하나부터 시작
- 얼굴 crop pipeline 검증
- subject split 확인
- metric 계산 검증
- frame baseline 수행

## Phase 2 — Source-only Video Baseline

비교:

```text
Frame baseline
vs
Video baseline
```

조건:

- same dataset protocol
- same train/test subjects
- same threshold policy

질문:

> Video temporal modeling 자체가 의미 있는가?

## Phase 3 — Cross-domain Baseline

예:

```text
Source: O + C + M
Target: I
```

정확한 dataset abbreviation은 project manifest에서 표준화.

비교:

- frame source-only
- video source-only

## Phase 4 — Naive DA

- full fine-tune on target bona-fide
- head-only fine-tune
- encoder frozen

목적:

> 실제로 spoof security regression이 발생하는지 증명.

## Phase 5 — Prototype / SFDA Baseline

가능하면 OTA/SDA-FAS 계열 재현 또는 단순 prototype baseline.

## Phase 6 — Proposed Spoof Preservation

Phase 4에서 문제가 확인된 이후에만 진행.

후보:

- prototype preservation
- margin loss
- source teacher distillation
- bounded adapter

## Phase 7 — Robustness

- multiple target datasets
- multiple attack types
- multiple seeds
- low-motion subset
- device-specific analysis

## Phase 8 — RGB + ToF

RGB 연구가 안정화된 후 확장.

---

# 30. 결과 해석 규칙

Claude는 다음 표현을 피한다.

```text
"이 모델이 더 좋다."
"DA가 성공했다."
"Video가 확실히 우수하다."
```

대신 조건을 포함한다.

좋은 예:

> OCM→I protocol의 seed 3개 평균에서 Video baseline의 AUC는 frame baseline보다 높았지만, Replay APCER 차이는 통계적으로 명확하지 않았다.

> Bona-fide-only fine-tuning은 BPCER를 낮췄으나 phone replay APCER를 증가시켜 security regression으로 분류했다.

연구 결과는 반드시:

- dataset
- protocol
- seed
- metric
- threshold policy

와 함께 표현한다.

---

# 31. 통계와 Seed

가능하면 주요 결과는 최소 3 seeds.

기록:

```text
mean
std
individual runs
```

한 번의 우연한 좋은 run을 SOTA처럼 해석하지 않는다.

논문 재현에서는 먼저 원 논문 seed/protocol을 맞추고 이후 multi-seed를 수행한다.

---

# 32. 추론 속도

PAD 제품을 고려하므로 다음을 기록한다.

- clip length
- resolution
- pre-processing 포함 여부
- face detector 포함 여부
- batch size
- device
- warmup
- number of repetitions
- latency ms/clip
- FPS equivalent
- memory

`inference_time / 1000` 같은 단위 변환은 명시적으로 관리한다.

예:

```text
milliseconds → seconds = ms / 1000
```

모델 inference와 전체 system latency를 혼동하지 않는다.

---

# 33. iBeta / ISO 관련 규칙

iBeta와 ISO 30107 관련 기준은 보안 인증과 연결되므로 다음을 지킨다.

- 최신 공식 자료 확인
- Level 1/Level 2 표현과 attack instrument 범위 확인
- 성능 기준을 기억으로 작성하지 않음
- 인증 시험 조건과 academic dataset 성능을 동일시하지 않음
- `AUC 99% = iBeta 통과` 같은 추론 금지

연구 metric은 인증 준비의 근거일 뿐 실제 인증 결과를 보장하지 않는다.

---

# 34. Data Governance / Privacy

얼굴 영상은 민감한 biometric data로 간주한다.

Claude Code는 다음을 자동 수행하지 않는다.

- public GitHub upload
- 외부 cloud upload
- raw face frame을 issue/log에 embed
- dataset 샘플을 공개 report에 저장

로그에는 dataset path 전체를 넣기보다 logical dataset ID를 사용한다.

예:

```text
dataset_id: replay_attack_v1
```

---

# 35. 실험 실패도 저장

실패한 experiment를 삭제하지 않는다.

예:

```text
status:
- success
- failed_environment
- failed_training
- invalid_protocol
- security_regression
- inconclusive
```

실패 이유가 다음 실험의 정보다.

---

# 36. Claude가 세션 시작 시 해야 할 것

이 저장소에서 작업 요청을 받으면 먼저:

```text
1. CLAUDE.md 읽기
2. git status 확인
3. repository tree 확인
4. research/decisions 확인
5. 현재 experiment registry 확인
6. 관련 config 확인
7. 요청을 Research / Code / Experiment / Analysis로 분류
```

이미 존재하는 구현을 새로 만들기 전에 반드시 검색한다.

---

# 37. 작업 유형별 행동 규칙

## Research 요청

```text
Primary paper search
→ source verify
→ paper review
→ claim DB
→ 연구와 연결
```

## Reproduction 요청

```text
official repo 확인
→ commit pin
→ environment 확인
→ dataset protocol 확인
→ smoke test
→ baseline result
```

## 새 아이디어 요청

```text
기존 baseline 확인
→ failure mode 확인
→ 최소 가설
→ 최소 ablation 설계
```

## Full experiment 요청

```text
spec
→ validation
→ smoke test
→ full-run flag
→ MLflow
→ evaluation
→ reviewer
```

---

# 38. Claude Code가 처음 구축해야 할 MVP

아직 저장소가 없다면 다음 순서대로 진행한다.

## Task 1 — Environment Inspection

먼저 확인:

```text
OS
Python
GPU
nvidia-smi
CUDA
PyTorch
disk
git
scheduler(Slurm 여부)
```

사용자의 현재 연구 환경은 H100 GPU를 사용한 경험이 있으나 **현재 machine이 H100이라고 가정하지 않는다.**

## Task 2 — Scaffold

위 repository structure 생성.

## Task 3 — Python environment

- `pyproject.toml`
- `uv.lock`
- ruff
- pytest
- hydra-core
- mlflow
- scikit-learn
- 필요한 torch stack

PyTorch/CUDA는 현재 서버 환경을 확인한 후 설치한다.

## Task 4 — Protocol schema

Pydantic/dataclass 중 하나로 validation.

## Task 5 — Metrics

다음 metric부터 구현 + unit test.

- APCER
- BPCER
- ACER
- HTER
- ROC AUC

## Task 6 — MLflow

local MVP.

## Task 7 — Dataset Manifest

dataset raw path와 metadata를 분리.

## Task 8 — First baseline

가장 작은 dataset + frame baseline.

## Task 9 — Video baseline

4/8 frame smoke test.

## Task 10 — DA baseline

full fine-tune / head-only부터 시작.

---

# 39. 구현하지 말아야 할 것 — 초기 과설계 방지

Phase 0에서 다음은 만들지 않는다.

- Kubernetes
- Ray cluster
- 복잡한 multi-agent swarm
- 10개 이상의 agent
- 자체 vector DB
- 자체 experiment dashboard
  - **2026-09-19 개정(ADR-006)**: MLflow run·registry·report 산출물을 읽기 전용으로 렌더링하는 로컬 정적 대시보드는 예외로 허용한다. 실험을 실행하거나 config를 바꾸는 control plane, 상시 서버, DB, 인증은 여전히 만들지 않는다.
- LangGraph service
- 복잡한 data lake

필요해질 때 추가한다.

현재 중요한 것은:

```text
재현 가능성
+
protocol integrity
+
metric integrity
+
research traceability
```

다.

---

# 40. LangGraph 추가 판단 기준

다음 3개 이상이 필요해지면 검토한다.

- 연구 루프를 비대화형으로 수시간/수일 실행
- 실패 후 checkpoint resume
- 여러 agent 상태의 persistent coordination
- human approval state를 서비스로 관리
- experiment queue orchestration
- scheduled literature monitoring

그 전에는 Claude Code + Python harness로 충분하다.

---

# 41. 하네스가 지켜야 할 가장 중요한 원칙 10개

1. **Paper claim은 primary source로 검증한다.**
2. **Protocol이 다르면 metric을 직접 비교하지 않는다.**
3. **Target adaptation sample과 test sample leakage를 막는다.**
4. **AUC만 보고 PAD 성공을 판단하지 않는다.**
5. **DA 전후 공격별 APCER를 반드시 비교한다.**
6. **Real-only DA는 기본적으로 security regression 가능성을 의심한다.**
7. **Source spoof knowledge를 잃는지 측정한다.**
8. **실패한 experiment도 기록한다.**
9. **LLM이 직접 장시간 GPU command를 즉흥 실행하지 않고 spec→validation을 통과한다.**
10. **복잡한 Proposed model보다 문제 존재를 baseline으로 먼저 증명한다.**

---

# 42. 현재 가장 중요한 연구 가설

## H1 — Video advantage

> Passive low-motion 환경에서도 multi-frame temporal modeling은 frame-only PAD보다 일부 spoof attack에 추가 단서를 제공한다.

## H2 — Real-only adaptation regression

> Target bona-fide만 이용한 unrestricted fine-tuning은 Target bona-fide acceptance를 개선할 수 있지만 일부 spoof attack의 APCER를 악화시킬 수 있다.

## H3 — Constrained adaptation

> Encoder freezing, prototype preservation 또는 spoof-preserving regularization을 사용하면 naive fine-tuning보다 보안 성능 저하를 줄이면서 domain adaptation 이점을 얻을 수 있다.

## H4 — Video-specific DA

> Frame-level adaptation보다 clip-level spatio-temporal adaptation이 video domain shift를 더 직접적으로 처리할 수 있다.

H4는 특히 아직 강하게 증명되지 않은 가설이며 결과에 따라 폐기할 수 있다.

---

# 43. 1차 실험 매트릭스

| ID | Backbone | Input | DA | Target Data | 목적 |
|---|---|---|---|---|---|
| E01 | Frame baseline | 1 frame | None | None | Source-only baseline |
| E02 | Video baseline | 8 frames | None | None | Temporal gain |
| E03 | Video baseline | 8 frames | Full FT | Real only | 위험한 naive DA |
| E04 | Video baseline | 8 frames | Head only | Real only | restricted DA |
| E05 | Video baseline | 8 frames | Prototype | Real only | source knowledge preservation |
| E06 | Video baseline | 8 frames | Prototype | Real+Spoof few-shot | idealized comparison |
| E07 | Video baseline | 8 frames | Proposed | Real only | final hypothesis |

반드시 E03을 측정해야 Proposed의 필요성을 주장할 수 있다.

---

# 44. 연구 결과 Report Template

각 experiment group 결과는 다음 template을 사용한다.

```markdown
# Experiment Report

## Research Question

## Hypothesis

## Protocol
- Source
- Target
- Adaptation data
- Test split
- Attack types
- Threshold rule
- Protocol hash

## Model

## Training

## Results

### Overall
| Metric | Baseline | Method | Delta |

### Per Attack
| Attack | APCER Baseline | APCER Method | Delta |

## Security Regression Check

## Seed Variance

## Failure Analysis

## Interpretation

## What This Does NOT Prove

## Next Experiment

## MLflow Runs

## Git Commit
```

---

# 45. Claude의 설명 스타일

사용자가 연구 개념을 물으면 다음 순서로 설명한다.

```text
1. 한 문장 결론
2. 직관적인 예시
3. 기술적 구조
4. 모델/수식
5. 현재 연구와 연결
```

예를 들어 DA 설명 시 바로 KL divergence부터 시작하지 않는다.

하지만 코드 구현이나 논문 재현 요청에서는 충분히 기술적으로 답한다.

---

# 46. 연구 아이디어를 제안할 때의 규칙

Claude는 아이디어를 다음 세 종류로 명확히 표시한다.

### [Established]
논문에서 이미 검증된 방법.

### [Adaptation]
기존 논문 아이디어를 이 프로젝트에 적용.

### [Hypothesis]
아직 검증되지 않은 신규 아이디어.

예:

```text
[Established]
OTA는 prototype 기반 source-free adaptation을 제안한다.

[Adaptation]
이를 video clip embedding에 적용할 수 있다.

[Hypothesis]
Clip-level OT adaptation이 frame-level OT보다 low-motion replay에서 우수할 수 있다.
```

세 가지를 섞어서 모두 논문 사실처럼 말하지 않는다.

---

# 47. 연구 우선순위

현재 우선순위:

```text
P0  Harness integrity
P0  Dataset / protocol correctness
P0  PAD metric correctness

P1  Video baseline
P1  Real-only DA regression 확인

P2  Prototype / preservation DA
P2  Low-motion evaluation

P3  RGB + ToF
P3  deployment optimization
```

---

# 48. 처음 Claude Code에 줄 추천 프롬프트

이 CLAUDE.md가 프로젝트 root에 저장된 후 Claude Code에 다음처럼 요청한다.

```text
CLAUDE.md를 프로젝트의 최상위 연구 규칙으로 읽어.

아직 코드를 대량 작성하지 말고 먼저 현재 저장소와 실행 환경을 분석해.
1. 현재 repository 구조
2. Python/PyTorch/CUDA/GPU 환경
3. 기존 PAD 코드와 데이터셋 adapter 유무
4. 기존 실험 결과나 로그
5. 구현 가능한 Harness MVP 항목
을 정리해.

그 다음 CLAUDE.md의 Phase 0을 구현하기 위한 작업을 의존성 순서대로 계획하고,
불필요한 multi-agent/분산 인프라는 추가하지 마.

가장 먼저 protocol schema, PAD metrics unit test, experiment spec validation,
MLflow tracking skeleton을 구축하는 방향을 우선해.
기존 코드가 있으면 새로 만들지 말고 재사용 가능성을 먼저 분석해.
```

---

# 49. Definition of Done — Harness MVP

MVP는 다음이 모두 만족되어야 완료로 본다.

- [ ] root `CLAUDE.md`
- [ ] `.claude/rules/`
- [ ] 3개 subagent
- [ ] destructive-command safety hook
- [ ] experiment launch validation
- [ ] uv-based environment
- [ ] Hydra config
- [ ] dataset manifest
- [ ] protocol schema
- [ ] protocol hash
- [ ] APCER unit test
- [ ] BPCER unit test
- [ ] ACER unit test
- [ ] HTER unit test
- [ ] AUC unit test
- [ ] MLflow run logging
- [ ] Git SHA logging
- [ ] environment metadata logging
- [ ] smoke-test mode
- [ ] full GPU run gate
- [ ] experiment report generator
- [ ] research claim store
- [ ] ADR structure

---

# 50. Definition of Done — Research Phase 1

다음 질문에 실제 숫자로 답할 수 있어야 한다.

> 같은 protocol에서 frame model과 video model 중 어떤 것이 더 나은가?

반드시 포함:

- APCER
- BPCER
- HTER/AUC
- per-attack APCER
- seed variance
- latency

---

# 51. Definition of Done — Research Phase 2

다음 질문에 답할 수 있어야 한다.

> Target Bona-fide-only adaptation이 Target 정상 사용자 성능을 개선하는 동시에 Spoof rejection을 악화시키는가?

비교:

```text
Source-only
vs
Full fine-tune
vs
Head-only
vs
Prototype adaptation
```

---

# 52. Definition of Done — Proposed 연구

Proposed method는 다음을 만족해야 의미가 있다.

```text
Target usability improvement
        +
No material spoof security regression
```

즉:

- BPCER만 좋아지는 것은 부족
- AUC만 좋아지는 것도 부족
- 특정 주요 attack의 APCER가 크게 악화되면 실패 가능성이 높음

Trade-off가 있다면 숨기지 않고 Pareto 관점으로 제시한다.

---

# 53. Open Questions

Claude는 아래 질문을 해결해야 할 backlog로 유지한다.

1. G²V²former 공식 code가 현재 완전히 공개되어 있는가?
2. TTN 재현 가능한 공식 implementation이 있는가?
3. 현재 보유 SiW-M 버전과 논문 protocol의 정확한 차이는 무엇인가?
4. AIHub Liveness dataset의 attack taxonomy와 subject split은 무엇인가?
5. Target 실제 디바이스 영상 수집이 가능한가?
6. Target에서 spoof를 소량 의도적으로 수집할 수 있는가?
7. Real-only라는 연구 설정이 실제 운영 제약인지, 단순 연구 설정인지?
8. target adaptation을 device별로 할지 site별로 할지?
9. on-device adaptation인지 server-side adaptation인지?
10. RGB 이후 ToF fusion 단계에서 DA를 modality별로 할지 joint하게 할지?
11. iBeta 최신 시험 요구사항과 현재 attack 범위 간 gap은?
12. low-motion clip을 어떻게 객관적으로 정의할 것인가?

---

# 54. 최종 원칙

이 프로젝트에서 하네스의 목적은 Claude를 더 자율적으로 만드는 것이 아니다.

**Claude가 틀리기 어려운 연구 시스템을 만드는 것**이 목적이다.

```text
좋은 Harness

= 더 많은 Agent

가 아니라

= 근거가 남음
+ Protocol이 잠김
+ 실험이 재현됨
+ 잘못된 비교가 차단됨
+ 공격 성능 악화가 숨겨지지 않음
+ 실패도 기록됨
```

따라서 언제나:

> **Evidence → Hypothesis → Controlled Experiment → Security-aware Evaluation → Review → Next Hypothesis**

순서를 유지한다.

---

# Appendix A. Research Flow

```text
                    Research Question
                           │
                           ▼
                  Literature Search
                           │
                           ▼
                    Evidence Verify
                           │
                           ▼
                      Hypothesis
                           │
                           ▼
                  Experiment Spec
                           │
                           ▼
                   Protocol Validate
                           │
                           ▼
                      Smoke Test
                           │
                           ▼
                   Approved Full Run
                           │
                           ▼
                       MLflow
                           │
                           ▼
           APCER / BPCER / ACER / HTER / AUC
                           │
                           ▼
               Security Regression Gate
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
          Supported                 Rejected
              │                         │
              └────────────┬────────────┘
                           ▼
                     Reviewer
                           │
                           ▼
                   Next Hypothesis
```

---

# Appendix B. Proposed System Concept

```text
                  SOURCE TRAINING

           Bona-fide           Spoof
               │                 │
               └──────┬──────────┘
                      ▼
               Video Encoder
                      │
                      ▼
                Clip Features
                      │
             ┌────────┴────────┐
             ▼                 ▼
       Real Prototype     Spoof Prototype


                 TARGET ADAPTATION

              Target Real Video
                      │
                      ▼
              Video Encoder 🔒/△
                      │
                      ▼
               Clip Embedding
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
 Domain adaptation          Spoof preservation
        │                           │
        └─────────────┬─────────────┘
                      ▼
                 Real / Spoof
```

`🔒/△`의 의미:
- 처음에는 freeze
- 실험 결과에 따라 일부 adapter만 trainable
- 전체 encoder fine-tuning은 baseline으로만 사용

---

# Appendix C. 핵심 참고자료

1. Liu et al., **Learning Deep Models for Face Anti-Spoofing: Binary or Auxiliary Supervision**, CVPR 2018  
   https://openaccess.thecvf.com/content_cvpr_2018/html/Liu_Learning_Deep_Models_CVPR_2018_paper.html

2. Yu et al., **Searching Central Difference Convolutional Networks for Face Anti-Spoofing**, CVPR 2020  
   https://openaccess.thecvf.com/content_CVPR_2020/html/Yu_Searching_Central_Difference_Convolutional_Networks_for_Face_Anti-Spoofing_CVPR_2020_paper.html

3. Wang et al., **Learning Multi-Granularity Temporal Characteristics for Face Anti-Spoofing**, IEEE TIFS 2022  
   https://ieeexplore.ieee.org/document/9730902/

4. Yang et al., **G²V²former: Graph Guided Video Vision Transformer for Face Anti-Spoofing**, IEEE TIFS 2025  
   https://doi.org/10.1109/TIFS.2025.3586506  
   https://arxiv.org/abs/2408.07675

5. Liu et al., **Source-Free Domain Adaptation with Contrastive Domain Alignment and Self-Supervised Exploration for Face Anti-Spoofing**, ECCV 2022  
   https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/362_ECCV_2022_paper.php

6. Guo et al., **Multi-Domain Learning for Updating Face Anti-Spoofing Models**, ECCV 2022  
   https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/7360_ECCV_2022_paper.php

7. Liu et al., **Source-Free Domain Adaptation With Domain Generalized Pretraining for Face Anti-Spoofing**, IEEE TPAMI 2024  
   https://doi.org/10.1109/TPAMI.2024.3370721

8. He et al., **Category-Conditional Gradient Alignment for Domain Adaptive Face Anti-Spoofing**, IEEE TIFS 2024  
   https://doi.org/10.1109/TIFS.2024.3486098

9. Li et al., **Optimal Transport-Guided Source-Free Adaptation for Face Anti-Spoofing**, CVPR 2025  
   https://openaccess.thecvf.com/content/CVPR2025/html/Li_Optimal_Transport-Guided_Source-Free_Adaptation_for_Face_Anti-Spoofing_CVPR_2025_paper.html

10. Claude Code Best Practices  
    https://code.claude.com/docs/en/best-practices

11. Claude Code Hooks  
    https://code.claude.com/docs/en/hooks-guide

12. Claude Code Subagents  
    https://code.claude.com/docs/en/sub-agents

13. LangGraph  
    https://docs.langchain.com/oss/python/langgraph/overview

14. Hydra  
    https://hydra.cc/docs/intro/

15. MLflow Tracking  
    https://mlflow.org/docs/latest/ml/tracking

16. DVC  
    https://dvc.org/doc

---

# 부록 D. 개정 이력

이 문서를 수정하는 것은 연구 방향 또는 운영 규칙의 변경이다(문서 서두 참조). 개정할 때마다 아래에 한 줄을 추가하고,
같은 커밋에서 `conventions.CONTRACT_SHA256`과 pin된 테스트·hook·문서의 sha256을 함께 갱신한다.

| 날짜 | 절 | 변경 | 근거 |
|---|---|---|---|
| 2026-09-19 | §39 | "자체 experiment dashboard" 금지에 **읽기 전용 로컬 정적 대시보드** 예외를 추가 | ADR-006 |
