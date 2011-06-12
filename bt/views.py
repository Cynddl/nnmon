from forms import AddViolation
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.core.files import File
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ObjectDoesNotExist
from django.contrib import messages
from models import Violation, Attachment, Comment
from tempfile import mkstemp
from datetime import datetime
import hashlib, os, re, json, smtplib
from random import randint
from email.mime.text import MIMEText
from urlparse import urljoin
from BeautifulSoup import BeautifulSoup, Comment as BComment

def sanitizeHtml(value, base_url=None):
    rjs = r'[\s]*(&#x.{1,7})?'.join(list('javascript:'))
    rvb = r'[\s]*(&#x.{1,7})?'.join(list('vbscript:'))
    re_scripts = re.compile('(%s)|(%s)' % (rjs, rvb), re.IGNORECASE)
    validTags = 'p i strong b u a h1 h2 h3 pre br img'.split()
    validAttrs = 'href src width height'.split()
    urlAttrs = 'href src'.split() # Attributes which should have a URL
    soup = BeautifulSoup(value)
    for comment in soup.findAll(text=lambda text: isinstance(text, BComment)):
        # Get rid of comments
        comment.extract()
    for tag in soup.findAll(True):
        if tag.name not in validTags:
            tag.hidden = True
        attrs = tag.attrs
        tag.attrs = []
        for attr, val in attrs:
            if attr in validAttrs:
                val = re_scripts.sub('', val) # Remove scripts (vbs & js)
                if attr in urlAttrs:
                    val = urljoin(base_url, val) # Calculate the absolute url
                tag.attrs.append((attr, val))

    return soup.renderContents().decode('utf8')

def activate(request):
    v=Violation.objects.get(activationid=request.GET.get('key','asdf'))
    v.activationid=''
    v.save()
    messages.add_message(request, messages.INFO, _('Thank you for verifying your submission.'))
    return HttpResponseRedirect('/') # Redirect after POST

def add(request):
    if request.method == 'POST':
        form = AddViolation(request.POST)
        if form.is_valid():
            actid = hashlib.sha1(''.join([chr(randint(32, 122)) for x in range(12)])).hexdigest()
            msg = MIMEText(_("Your verification key is %s/activate?key=%s\n") % (settings.ROOT_URL or 'http://localhost:8001/',actid))
            msg['Subject'] = _('NNMon submission verification')
            msg['From'] = 'nnmon@nnmon.lqdn.fr'
            msg['To'] = form.cleaned_data['email']
            s = smtplib.SMTP('localhost')
            s.sendmail('nnmon@nnmon.lqdn.fr', [form.cleaned_data['email']], msg.as_string())
            s.quit()
            v=Violation(
                country = form.cleaned_data['country'],
                operator = form.cleaned_data['operator'],
                contract = form.cleaned_data['contract'],
                resource = form.cleaned_data['resource'],
                resource_name = form.cleaned_data['resource_name'],
                type = form.cleaned_data['type'],
                media = form.cleaned_data['media'],
                temporary = form.cleaned_data['temporary'],
                contractual = form.cleaned_data['contractual'],
                contract_excerpt = sanitizeHtml(form.cleaned_data['contract_excerpt']),
                loophole = form.cleaned_data['loophole'],
                activationid = actid
                )
            v.save()
            c = Comment(
                comment=form.cleaned_data['comment'],
                submitter_email=form.cleaned_data['email'],
                submitter_name=form.cleaned_data['nick'],
                timestamp=datetime.now(),
                violation=v,
                )
            c.save()
            for f in request.FILES.getlist('attachments[]'):
                a=Attachment(comment=c, name=f.name)
                m = hashlib.sha256()
                for chunk in f.chunks():
                    m.update(chunk)
                sname=m.hexdigest()
                a.storage.save(sname,f)
                a.save()

            messages.add_message(request, messages.INFO, _('Thank you for submitting this report, you will receive a verification email shortly.'))
            return HttpResponseRedirect('/') # Redirect after POST
    else:
        form = AddViolation()

    return render_to_response(
        'add.html',
        { 'form': form, },
        context_instance=RequestContext(request))

def ajax(request, country=None, operator=None):
    if not operator:
        return HttpResponse(json.dumps(sorted(list(set([x.operator for x in Violation.objects.filter(country=country,activationid='')])))))
    else:
        return HttpResponse(json.dumps(sorted(list(set([x.contract for x in Violation.objects.filter(country=country,activationid='',operator=operator)])))))

def index(request):
    v_list = Violation.objects.filter(activationid='')
    paginator = Paginator(v_list, 25)

    page = request.GET.get('page','1')
    try:
        violations = paginator.page(page)
    except PageNotAnInteger:
        violations = paginator.page(1)
    except EmptyPage:
        violations = paginator.page(paginator.num_pages)

    return render_to_response('list.html', {"violations": violations},context_instance=RequestContext(request))

def view(request,id):
    v = get_object_or_404(Violation, pk=id)
    return render_to_response('view.html', { 'v': v, },context_instance=RequestContext(request))
