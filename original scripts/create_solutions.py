from pathlib import Path
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent.parent/'output/pdf'
pdfmetrics.registerFont(TTFont('Study','/System/Library/Fonts/Supplemental/Times New Roman.ttf'))
pdfmetrics.registerFont(TTFont('StudyBold','/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf'))
pdfmetrics.registerFontFamily('Study',normal='Study',bold='StudyBold',italic='Study',boldItalic='StudyBold')
title=ParagraphStyle('Title',fontName='StudyBold',fontSize=21,leading=26,textColor=HexColor('#163D62'),spaceAfter=9)
small=ParagraphStyle('Small',fontName='Study',fontSize=10,leading=13,spaceAfter=12)
body=ParagraphStyle('Body',fontName='Study',fontSize=11,leading=15,spaceAfter=11)

answers=[
('1','(b) Discrete.','X can take only the four listed values, so its distribution is discrete.'),
('2','True.','P(X &lt; 1) = Φ(1), whereas P(Y &lt; 1) = Φ(1/1.5). The standard normal CDF is increasing.'),
('3','(b) Poisson distribution.','Model the number of emails in the specified day as Poisson with mean 21.7.'),
('4','(a) Population mean equals 55.','A null hypothesis concerns a population parameter and includes equality.'),
('5','(c).',"De Morgan's law gives (A ∪ B)′ = A′ ∩ B′, rather than A′ ∪ B′."),
('6','16.','By independence, Var(2X − Y) = 4 Var(X) + Var(Y) = 4(3) + 4 = 16.'),
('7','125/1944 ≈ 0.0643004.','For the second six to occur on roll 5, there must be exactly one six in the first four rolls and a six on roll 5: 4(1/6)<super>2</super>(5/6)<super>3</super>.'),
('8','False.','SD(sample mean) = σ/√n. Doubling n divides this standard deviation by √2; quadrupling n halves it.'),
('9','False.','A discrete random variable can have an infinite or undefined expectation. A finite expectation requires convergence of the relevant weighted sum.'),
('10','True.','There is no probability in the interval (0, 10), so its complementary event {X ≤ 0 or X ≥ 10} has probability 1.'),
('11','(d).','A valid CDF must be nondecreasing and right-continuous, with limits 0 and 1 at the two infinities. Only (d) satisfies all these conditions.'),
('12','False.','Variance alone does not determine estimator quality: MSE = variance + bias<super>2</super>. A lower-variance estimator may have a larger bias.'),
('13','(d), exp(−1) ≈ 0.367879.','P(X &gt; 5 | X &gt; 3) = exp(−5/2)/exp(−3/2) = exp(−1), by the memoryless property.'),
('14','(a).','Repeated independent flips of the same coin are identically distributed Bernoulli observations. The other samples restrict the sampling frame relative to the stated population.'),
('15','(c).','Under the usual finite-variance CLT conditions, the sampling distribution of the mean is approximately normal for sufficiently large sample size.'),
('16','716/729 ≈ 0.9821674.','Let K ~ Binomial(6, 2/3). P(K ≥ 2) = 1 − (1/3)<super>6</super> − 6(2/3)(1/3)<super>5</super> = 716/729. The published value 0.6488 is incorrect.'),
('17','1 − Φ(0.4) ≈ 0.3445783.','The independent total score is approximately N(330, 625), with standard deviation 25. Thus P(total &gt; 340) = P(Z &gt; (340 − 330)/25).'),
('18','t ≈ 1.790421, with 7 degrees of freedom.','Use paired differences A − B: mean difference = 1.75 and sample variance = 107/14. The statistic is 1.75 / √[(107/14)/8].'),
]

# The rest of the independently checked answers are added below.
TAIL=[
('19','(192.2, 207.8) days.','With known population SD, the 95% confidence interval is 200 ± 1.96(40/√100) = (192.16, 207.84). Round the endpoints to one decimal place.'),
('20','1/36 ≈ 0.0278.','The sum is 5 for the three permutations of (1,1,3) and the three permutations of (1,2,2). Thus the probability is 6/6<super>3</super> = 1/36.'),
('21','True.','The observed sample mean is positive, so the observed z statistic is positive. The upper-tail p-value is 1 − Φ(z), and the two-sided p-value is twice this.'),
('22','5/77 ≈ 0.0649.','By Bayes\' rule: P(infected | negative) = [0.25(0.2)] / [0.25(0.2) + 0.90(0.8)] = 0.05/0.77.'),
('23','(b), (c).','Rejection places the observed statistic in the rejection region. If the null is actually true, this rejection is a type I error. A type II error requires not rejecting the null.'),
('24','Approximately 0.3085.','The CLT gives S = sum of the 100 variables approximately N(500, 400). Hence P(S &gt; 510) ≈ P(Z &gt; (510 − 500)/20) = 1 − Φ(0.5).'),
('25','(b).','An event can omit a possible outcome of probability zero and still have probability 1. For example, if X is uniform on [0,1], the event X &gt; 0 excludes zero but has probability 1.'),
('26','15/1024 = 0.0146484375.','The first win in round 4 requires losses in rounds 1, 2 and 3, followed by a win in round 4. Independence gives (1/2)(1/4)(1/8)(15/16).'),
('27','(a), Φ(−3) − Φ(−7).','The standard error is 2/√25 = 0.4. Not rejecting means −0.8 ≤ sample mean ≤ 0.8. Under true mean 2, standardizing these bounds gives −7 and −3.'),
('28','True.','The density is nonnegative. Each half integrates to 1/2, so the total integral is 1. Symmetry about θ gives population mean θ.'),
('29','(d): (70, 75), 9.19%.','A B grade lies between 1 and 1.5 standard deviations above the mean: 60 + 10 = 70 to 60 + 15 = 75. The fraction is Φ(1.5) − Φ(1) ≈ 0.091848.'),
('30','(a), 1/6.','Given heads, reporting 6 has probability 1/6. Given tails, the two dice must sum to 7, also with probability 6/36. Therefore the mixture is p/6 + (1 − p)/6 = 1/6.'),
('31','0.327 (to three decimal places).','The favorable (X₁, X₂, X₃) triples are (0,1,1) and (1,0,2). Their total probability is 4 exp(−4). Since Y₂ ~ Poisson(3), P(Y₂ = 2) = (9/2)exp(−3). The ratio is (8/9)exp(−1) ≈ 0.32700395; the published 0.1804 is incorrect.'),
('32','13/28 ≈ 0.4643 (to four decimal places).','Odd winnings occur for X = 1, or for X = 3 followed by tails. P(X = 1) = C(3,1)C(5,3)/C(8,4) = 3/7 and P(X = 3) = 1/14. Thus 3/7 + (1/2)(1/14) = 13/28. The published 0.4642 is incorrectly rounded.'),
('33','(c), 3/8.','The first part of the density integrates to 2k/3. For x &gt; 1, the integral of k exp((1 − x)/2) is 2k. Normalization gives (2/3 + 2)k = 1, so k = 3/8.'),
('34','(a), (d).','Centering X and Y at their sample means gives expected sums of squares (n₁ − 1)σ² and (n₂ − 1)σ². Centering U at its known mean 4 contributes n₃σ², giving denominator n₁ + n₂ + n₃ − 2. Centering U at its sample mean instead contributes (n₃ − 1)σ², giving denominator n₁ + n₂ + n₃ − 3.'),
('35','1/10 = 0.1.','For t ≥ 0, P(T &gt; t) = product of P(Xᵢ &gt; t) = [exp(−t)]<super>10</super> = exp(−10t). Thus T has an exponential distribution with rate 10 and mean 1/10.'),
]

def footer(c,doc):
    c.setFont('Study',9);c.setFillColor(HexColor('#526273'))
    c.drawString(44,29,'ST2334 • AY 2022/23 Semester I • Checked worked solutions')
    c.drawRightString(A4[0]-44,29,str(9+doc.page))

def main():
    entries=answers+TAIL
    assert len(entries)==35
    story=[]
    groups=[entries[:9],entries[9:18],entries[18:27],entries[27:]]
    for g,group in enumerate(groups):
        if g:story.append(PageBreak())
        story.append(Paragraph('Worked solutions' if g==0 else 'Worked solutions continued',title))
        story.append(Paragraph(f'Questions {group[0][0]}–{group[-1][0]}',small))
        if g==0:
            story.append(Paragraph('Independently checked study solutions, rather than a reproduction of the uploaded key. Corrections include Q16, Q31 and the four-decimal rounding in Q32. Questions appear on pages 1–9.',small))
        for n,answer,reason in group:
            for char,replacement in {'∪':' union ','∩':' intersection ','₁':'<sub>1</sub>','₂':'<sub>2</sub>','₃':'<sub>3</sub>','ᵢ':'<sub>i</sub>'}.items():
                answer=answer.replace(char,replacement)
                reason=reason.replace(char,replacement)
            story.append(KeepTogether([Paragraph(f'<b>{n}. {answer}</b><br/>{reason}',body)]))
    buf=BytesIO()
    SimpleDocTemplate(buf,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=38,bottomMargin=46).build(story,onFirstPage=footer,onLaterPages=footer)
    questions_path=OUT/'ST2334_AY2022-23_Final_Example_Questions_Only.pdf'
    questions=PdfReader(questions_path)
    assert len(questions.pages)==9
    normalized=PdfWriter()
    for p in questions.pages:
        p.scale_to(*A4);normalized.add_page(p)
    normalized.add_metadata({'/Title':'ST2334 AY2022-23 Final Example Questions - Questions Only','/Subject':'Reconstructed from the publicly visible questions preview; cover reflowed for printing.'})
    with questions_path.open('wb') as f:normalized.write(f)
    combined=PdfWriter()
    for p in normalized.pages:combined.add_page(p)
    key=PdfReader(buf)
    assert len(key.pages)==4, f'Unexpected key length: {len(key.pages)}'
    for p in key.pages:combined.add_page(p)
    combined.add_outline_item('Questions',0)
    combined.add_outline_item('Checked worked solutions',9)
    combined.add_metadata({'/Title':'ST2334 AY2022-23 Final Example Questions - With Checked Solutions','/Subject':'35 original questions followed by independently checked worked solutions. Corrects published Q16, Q31 and Q32.'})
    with (OUT/'ST2334_AY2022-23_Final_Example_With_Solutions.pdf').open('wb') as f:combined.write(f)
    print('Created 9-page questions PDF and 13-page questions plus solutions PDF.')

if __name__=='__main__':main()
