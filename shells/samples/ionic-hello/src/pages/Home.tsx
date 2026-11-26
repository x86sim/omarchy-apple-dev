import { useState } from 'react';
import { IonButton, IonContent, IonHeader, IonPage, IonText, IonTitle, IonToolbar } from '@ionic/react';

import './Home.css';

const Home: React.FC = () => {
  const [taps, setTaps] = useState(0);
  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonTitle>Ionic on x86Sim</IonTitle>
        </IonToolbar>
      </IonHeader>
      <IonContent fullscreen className="ion-padding">
        <IonText>
          <p>Taps: {taps}</p>
        </IonText>
        <IonButton onClick={() => setTaps(taps + 1)}>Tap me</IonButton>
      </IonContent>
    </IonPage>
  );
};

export default Home;
