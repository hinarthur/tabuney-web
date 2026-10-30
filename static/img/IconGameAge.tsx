import React from 'react';
import { Svg, Path } from 'react-native-svg';

const IconGameAge = (props: any) => (
  <Svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 28 28"
    {...props} // 這樣可以讓使用者傳入額外的樣式或屬性
  >
    <Path
      d="M9,4C7.9,4,7,4.9,7,6s0.9,2,2,2s2-0.9,2-2S10.1,4,9,4z M7,9c-1.1,0-2,0.9-2,2v5c0,0.6,0.4,1,1,1h1v7h5V13.6
      l2.5,4.4H17l1-1.3V24h4v-5c0.6,0,1-0.4,1-1v-2c0-1.1-0.9-2-2-2h-2.5c-0.6,0-1.1,0.3-1.5,0.7c-0.3,0.4-0.7,0.9-1,1.3h-0.3L12,9.7
      C11.8,9.4,11.2,9,10.5,9H7z M20,10c-0.8,0-1.5,0.7-1.5,1.5S19.2,13,20,13s1.5-0.7,1.5-1.5S20.8,10,20,10z"
      fill="#0E8EDD" // 這邊也可以直接設定顏色，或者傳入 props 來動態改變顏色
    />
  </Svg>
);

export default IconGameAge;
