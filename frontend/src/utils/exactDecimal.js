// 比例转百分比只移动十进制位置，避免大金额/高精度值经过浮点运算。
export function percentText(value) {
 if (value == null) return null
 const match = String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/)
 if (!match) return `${value}（比例）`
 const fraction = (match[3] || '').padEnd(2, '0')
 const whole = `${match[2]}${fraction.slice(0, 2)}`.replace(/^0+(?=\d)/, '')
 const tail = fraction.slice(2).replace(/0+$/, '')
 return `${match[1]}${whole}${tail ? `.${tail}` : ''}%`
}
