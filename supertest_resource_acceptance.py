"""Post-warmup model RAM/allocated GPU memory drift, owned saved samples only."""
def evaluate(report):
    warm=[s for s in report['samples'] if s['elapsed']>=120 and s.get('model')]
    private=[s['model']['private_mib'] for s in warm]
    gpu=[g for s in report['samples'] if s['elapsed']>=120 for g in s.get('gpu',[]) if g.get('role')=='model' and g.get('dedicated_mib') is not None]
    dedicated=[g['dedicated_mib'] for g in gpu];shared=[g['shared_mib'] for g in gpu if g.get('shared_mib') is not None]
    span=lambda values:round(max(values)-min(values),2) if values else None
    checks={'model_private_ram_bounded':len(private)>=3 and span(private)<=64,'owned_dedicated_memory_bounded':span(dedicated)<=64 if len(dedicated)>=2 else None,'owned_shared_memory_bounded':span(shared)<=64 if len(shared)>=2 else None}
    return {'checks':checks,'warmup_seconds':120,'allowed_drift_mib':64,'model_private_ram_range_mib':span(private),'owned_dedicated_memory_range_mib':span(dedicated),'owned_shared_memory_range_mib':span(shared),'gpu_counter_samples':len(gpu),'passed':all(v is not False for v in checks.values()) and checks['model_private_ram_bounded'],'scope':'64 MiB tolerance during this fixed-input replay, not a universal no-leak proof. GPU counter absence is N/A.'}
if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('report');args=parser.parse_args();p=Path(args.report)
    r=json.loads(p.read_text(encoding='utf8'));r['resource_acceptance']=evaluate(r);r['passed']=r['passed'] and r['resource_acceptance']['passed'];p.write_text(json.dumps(r,indent=2),encoding='utf8');print(json.dumps(r['resource_acceptance']))
