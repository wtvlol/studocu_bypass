"""Make an A4 source copy and a practice copy with answer sections removed.

Marker-based detection is deliberately reviewable: writes a rectangle log and
checks the question sequence before and after saving. Always visually inspect.
"""
from pathlib import Path
import argparse,json,re
import pymupdf

def text_lines(page):
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            yield ''.join(s['text'] for s in line['spans']).strip(),pymupdf.Rect(line['bbox'])

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path)
    ap.add_argument('--marker',default='SOLUTION')
    ap.add_argument('--marker-regex',help='Override the literal marker with a regex, e.g. ^(?:Explanation|Answer)\\b')
    ap.add_argument('--question-pattern',default=r'^(\d+)\.\s*(?:MULTIPLE|FILL|TRUE)')
    ap.add_argument('--expected-questions',type=int)
    ap.add_argument('--solutions-source',type=Path,help='Optional unaltered solutions PDF when input has had its highlights cleared')
    ap.add_argument('--output-dir',type=Path,default=Path('output'))
    ap.add_argument('--name',default='Study_Paper')
    ap.add_argument('--top-content',type=float,default=0,help='Top of content in source PDF points; preserves running header above it')
    args=ap.parse_args()
    source=pymupdf.open(args.solutions_source or args.input);practice=pymupdf.open(args.input)
    if len(source)!=len(practice):raise ValueError('Solutions and practice sources must have the same page count')
    question_re=re.compile(args.question_pattern,re.I)
    marker_re=re.compile(args.marker_regex or (r'^'+re.escape(args.marker)+r'\b'),re.I)
    in_answer=False;seen=[];markers=0;log=[]
    for i,page in enumerate(practice):
        events=[]
        for text,rect in text_lines(page):
            q=question_re.match(text)
            if q:events.append((rect.y0,'question',q.group(1),rect))
            if marker_re.match(text):events.append((rect.y0,'answer',None,rect))
        start=args.top_content if in_answer else None
        rects=[]
        for y,kind,number,bbox in sorted(events):
            if kind=='question':
                seen.append(number)
                if in_answer and start is not None and y-2>start:
                    rects.append(pymupdf.Rect(0,start,page.rect.width,y-2))
                in_answer=False;start=None
            else:
                markers+=1
                if not in_answer:start=max(args.top_content,y-1)
                in_answer=True
        if in_answer and start is not None:
            rects.append(pymupdf.Rect(0,start,page.rect.width,page.rect.height))
        for rect in rects:
            page.add_redact_annot(rect,fill=(1,1,1))
            log.append({'page':i+1,'rect':list(rect)})
        # This deletes PDF text and image parts, rather than painting a removable box.
        page.apply_redactions(images=2,graphics=1,text=0)
    if not markers:raise ValueError('No answer markers found; refusing an unchanged practice copy')
    if args.expected_questions and len(seen)!=args.expected_questions:
        raise ValueError(f'Expected {args.expected_questions} questions, found {seen}')
    surviving=[q.group(1) for page in practice for text,_ in text_lines(page) if (q:=question_re.match(text))]
    if surviving!=seen:raise ValueError('Some question headings were removed')
    if any(marker_re.match(text) for page in practice for text,_ in text_lines(page)):
        raise ValueError('An answer marker survived')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for doc,suffix in [(source,'With_Solutions'),(practice,'Questions_Only')]:
        out=pymupdf.open()
        for i in range(len(doc)):
            page=out.new_page(width=595.2756,height=841.8898)
            page.show_pdf_page(page.rect,doc,i)
        out.set_metadata({'title':args.name.replace('_',' ')+' - '+suffix.replace('_',' '),
            'subject':'Reconstructed from the readable preview; practice copy has solution regions permanently removed.'})
        path=args.output_dir/(args.name+'_'+suffix+'.pdf')
        out.save(path,garbage=4,deflate=True)
        print(path.resolve())
    (args.output_dir/(args.name+'_redaction_log.json')).write_text(json.dumps(log,indent=2))
    print(f'Preserved {len(seen)} question headings and removed {markers} answer sections across {len(source)} pages.')

if __name__=='__main__':main()
