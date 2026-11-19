"""Create printable source-solutions and genuinely redacted practice copies."""
from pathlib import Path
import json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'python-deps'))
import pymupdf

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent.parent/'output/pdf'
SOURCE=ROOT/'sample-b-extracted.pdf'
source=pymupdf.open(SOURCE)
assert len(source)==12
question_re=re.compile(r'^(\d+)\.\s*(?:MULTIPLE|FILL|TRUE)')

def lines(page):
    result=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            text=''.join(s['text'] for s in line['spans']).strip()
            result.append((text,pymupdf.Rect(line['bbox'])))
    return result

questions=pymupdf.open(SOURCE)
state=False
seen=[];solution_count=0;rect_log=[]
for i,page in enumerate(questions):
    if i==0:
        for rect in page.search_for('Suggested Solutions'):
            page.add_redact_annot(rect,fill=(1,1,1))
        page.apply_redactions()
        continue
    events=[]
    footer=page.rect.height
    for text,rect in lines(page):
        m=question_re.match(text)
        if m:events.append((rect.y0,'question',int(m[1]),rect))
        if text=='SOLUTION':events.append((rect.y0,'solution',None,rect))
    start=42 if state else None
    rectangles=[]
    for y,kind,number,rect in sorted(events):
        if kind=='question':
            seen.append(number)
            if state and start is not None and y-4>start:
                rectangles.append(pymupdf.Rect(0,start,page.rect.width,y-4))
            state=False;start=None
        else:
            solution_count+=1
            if not state:start=y-2
            state=True
    if state and start is not None and footer>start:
        rectangles.append(pymupdf.Rect(0,start,page.rect.width,footer))
    for rect in rectangles:
        page.add_redact_annot(rect,fill=(1,1,1))
        rect_log.append({'page':i+1,'rect':list(rect)})
    page.apply_redactions(images=2,graphics=1,text=0)
    # Replace source footers consistently; mathematical digits are not page numbers.
    for text,rect in lines(page):
        if text==str(i+1) and rect.y0>page.rect.height*.9 and abs((rect.x0+rect.x1)/2-page.rect.width/2)<20:
            page.add_redact_annot(rect,fill=(1,1,1))
    page.apply_redactions(images=2,graphics=1,text=0)

assert seen==list(range(1,31)),seen
assert solution_count==30,solution_count
remaining='\n'.join(p.get_text() for p in questions)
assert 'SOLUTION' not in remaining.upper()
assert 'The answer is' not in remaining and 'The answers are' not in remaining
assert not any(span.get('color')==255 for p in questions for b in p.get_text('dict')['blocks'] for line in b.get('lines',[]) for span in line['spans']), 'A blue solution span survived'

def save_a4(doc,path,title,practice=False):
    normalized=pymupdf.open()
    for i in range(len(doc)):
        page=normalized.new_page(width=595.2756,height=841.8898)
        page.show_pdf_page(page.rect,doc,i)
        if practice:
            page.insert_font(fontname='StudyPage',fontfile='/System/Library/Fonts/Supplemental/Times New Roman.ttf')
            page.insert_text((294,815),str(i+1),fontname='StudyPage',fontsize=10)
    normalized.set_metadata({'title':title,'subject':'ST2334 AY2024/25 Semester I - Sample Paper B. Extracted from publicly readable preview; cover reflowed.'})
    normalized.set_toc([[1,'Cover and instructions',1],[1,'Questions',2]])
    normalized.save(path,garbage=4,deflate=True)
    return normalized

qpath=OUT/'ST2334_AY2024-25_Sample_B_Questions_Only.pdf'
spath=OUT/'ST2334_AY2024-25_Sample_B_With_Solutions.pdf'
save_a4(questions,qpath,'ST2334 AY2024-25 Sample B - Questions Only',practice=True)
notes=ROOT/'sample-b-notes.pdf'
if notes.exists():
    with pymupdf.open(notes) as note_doc:source.insert_pdf(note_doc)
save_a4(source,spath,'ST2334 AY2024-25 Sample B - Suggested Solutions')
(ROOT/'sample-b-redactions.json').write_text(json.dumps(rect_log,indent=2))
# Verify that all 30 question headings survived saving and that answers were removed.
check=pymupdf.open(qpath)
surviving=[]
for page in check:
    for text,_ in lines(page):
        m=question_re.match(text)
        if m:surviving.append(int(m[1]))
assert surviving==list(range(1,31)),surviving
assert not any('SOLUTION' in p.get_text().upper() for p in check)
print(f'Created two {len(check)}-page A4 PDFs; preserved all 30 questions and removed all 30 solution sections.')
