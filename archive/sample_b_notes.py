from pathlib import Path
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parent
for name,file in [('Study','Times New Roman.ttf'),('StudyBold','Times New Roman Bold.ttf')]:
    pdfmetrics.registerFont(TTFont(name,'/System/Library/Fonts/Supplemental/'+file))
pdfmetrics.registerFontFamily('Study',normal='Study',bold='StudyBold',italic='Study',boldItalic='StudyBold')
title=ParagraphStyle('Title',fontName='StudyBold',fontSize=23,leading=28,textColor=HexColor('#173f60'),spaceAfter=14)
body=ParagraphStyle('Body',fontName='Study',fontSize=12,leading=17,spaceAfter=19)
items=[
    ('Reading notes','The preceding pages preserve the published suggested solutions. These notes clarify a notation typo and two interpretation details.'),
    ('Question 13: expectation notation','For the example with X taking values 2<super>i</super>, the expectation is the sum of 2<super>i</super>P(X = 2<super>i</super>), over i = 1, 2, .... The initial factor i in the first displayed sum is a typo; the next step correctly uses 2<super>i</super>. The expectation diverges, so the answer remains FALSE.'),
    ('Question 14: implicit existence assumption','Option (c) is the intended answer: generally, the expectation of a ratio or nonlinear function cannot be found by simply substituting expectations. The other displayed expressions implicitly assume that their expectations and variances are well-defined. Finite Var(X) alone does not guarantee that E(exp(X)) is finite.'),
    ('Question 28: rounding of the supplied standard deviation','Using the table\'s supplied difference SD of 2.65 gives t = 6/(2.65/√3) = 3.921624..., hence the published answer 3.92. Recomputing the sample SD from the raw differences 9, 5 and 4 gives √7 = 2.645751..., and t = 3.927922..., which rounds to 3.93. The difference comes from rounding the SD before calculating the statistic.'),
]
story=[]
for i,(head,text) in enumerate(items):
    story.append(Paragraph(head,title if i==0 else ParagraphStyle('H'+str(i),parent=body,fontName='StudyBold',fontSize=14,spaceAfter=6)))
    story.append(Paragraph(text,body))
def footer(c,d):
    c.setFont('Study',9);c.setFillColor(HexColor('#506277'))
    c.drawString(45,28,'ST2334 Sample B • AY 2024/25 Semester I • Supplementary study notes')
    c.drawRightString(A4[0]-45,28,'13')
SimpleDocTemplate(str(ROOT/'sample-b-notes.pdf'),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=43,bottomMargin=48).build(story,onFirstPage=footer)
