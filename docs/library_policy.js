// Public-library quality policy, independent of numerical/physical feasibility.
export const SMALL_BODY_POLICY=Object.freeze({maxYearsExclusive:40,highC3:170,highC3MaxYearsExclusive:25});
export function smallBodyTarget(id){const n=Number(id);return n===9||n===999||n>=1000;}
export function smallBodyQualityReason(target,c3,years){
 if(!smallBodyTarget(target))return null;
 if(years>=SMALL_BODY_POLICY.maxYearsExclusive)return 'Small-body flight time must be below 40 years';
 if(c3>SMALL_BODY_POLICY.highC3&&years>=SMALL_BODY_POLICY.highC3MaxYearsExclusive)return 'Small-body flights above C3 170 must take less than 25 years';
 return null;
}
