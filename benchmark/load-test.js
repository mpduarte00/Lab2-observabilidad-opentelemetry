
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  summaryTrendStats: [
    'avg',
    'min',
    'med',
    'max',
    'p(90)',
    'p(95)',
    'p(99)',
  ],

  scenarios: {
    carga: {
      executor: 'constant-vus',
      vus: 50,
      duration: '5m',
    },
  },
};

export default function () {
  const response = http.get('http://127.0.0.1:8000/');

  check(response, {
    'respuesta HTTP 200': (r) => r.status === 200,
  });

  sleep(1);
}
