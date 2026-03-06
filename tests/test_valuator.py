#!/usr/bin/env python3
"""Test-Script für Domain-Valuator"""

import sys
sys.path.insert(0, 'src')
from valuator import DomainValuator

# Test-Domains mit erwarteten Mindest-Scores
test_domains = [
    ('ai.com', 50),
    ('cloudai.io', 45),
    ('my-super-long-domain-name.xyz', 10),
    ('techlab.ai', 45),
    ('pay.app', 40),
    ('crypto.bot', 40),
    ('aipay.io', 45),
    ('test123.info', 10),
    ('health.ai', 45),
    ('shop.de', 40),
]

print('='*70)
print('DOMAIN VALUATOR - TEST VALIDIERUNG')
print('='*70)
print('Domain'.ljust(35), 'Score'.ljust(8), 'Erwartet'.ljust(10), 'Status'.ljust(10))
print('-'*70)

valuator = DomainValuator('data/expired_domains.db')
high_potentials = []

for domain, expected_min in test_domains:
    v = valuator.evaluate_domain(domain, purchase_price=10.0)
    status = 'OK' if v.total_score >= expected_min else 'LOW'
    print(domain.ljust(35), str(v.total_score).ljust(8), ('>=' + str(expected_min)).ljust(10), status.ljust(10))
    if v.is_high_potential:
        high_potentials.append((domain, v.total_score, v.recommended_sale_price))

print('='*70)
print('\nHIGH POTENTIAL DOMAINS:')
for domain, score, price in high_potentials:
    print(f'  {domain} - Score: {score}/100 - Empfohlener Verkaufspreis: ${price:.2f}')

print('\n' + '='*70)
print(f'TEST ZUSAMMENFASSUNG:')
print(f'  Geprüfte Domains: {len(test_domains)}')
print(f'  High Potential: {len(high_potentials)}')
ok_count = sum(1 for d, e in test_domains 
               if valuator.evaluate_domain(d, 10.0).total_score >= e)
print(f'  Bestandene Tests: {ok_count}/{len(test_domains)}')
print('='*70)
