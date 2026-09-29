from linkone_body import locate
cases = [('MALE',0,40,58,'우측 대퇴부'),('MALE',0,67,58,'좌측 대퇴부'),('MALE',1,40,60,'좌측 대퇴부'),('MALE',0,53,36,'상복부'),('MALE',0,53,42,'하복부'),('FEMALE',0,40,58,'우측 대퇴부')]
for gender,view,x,y,label in cases:
    result=locate(gender,dict(view=view,x=x,y=y))
    assert result['label']==label, result
assert locate('MALE',dict(view=0,x=53,y=39))['status']=='boundary'
assert locate('FEMALE',dict(view=1,x=40,y=34))['status']=='ambiguous'
assert locate('MALE',dict(view=0,x=2,y=40))['status']=='unmapped'
print('9 example checks passed')
