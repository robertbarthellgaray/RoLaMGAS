import test from 'node:test';
import assert from 'node:assert/strict';
import {position} from '../docs/community.js';
test('public gallery samples two-body arcs with correct circular geometry',()=>{const AU=149597870.7,mu=132712440041.27942,speed=Math.sqrt(mu/AU),period=2*Math.PI*Math.sqrt(AU**3/mu);const r=position([AU,0,0],[0,speed,0],period/4);assert.ok(Math.abs(r[0])<.01);assert.ok(Math.abs(r[1]-AU)<.01);});
test('public gallery handles outbound hyperbolic trajectories',()=>{const r=position([149597870.7,0,0],[0,55,1],60*365.25*86400);assert.ok(r.every(Number.isFinite));assert.ok(Math.hypot(...r)>149597870.7*100);});
