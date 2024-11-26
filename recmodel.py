import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
import traceback

class RentalRecommender:
    def __init__(self, csv_path='rent_apts.csv'):
        try:
            self.df = pd.read_csv(csv_path)
            print(f"Loaded {len(self.df)} records from {csv_path}")
            print("Sample of raw data:")
            print(self.df.head())
            print("\nData types before conversion:", self.df.dtypes)
            
            # Ensure required columns exist
            required_columns = ['Price', 'Bedrooms', 'Bathrooms', 'Neighborhood']
            missing_columns = [col for col in required_columns if col not in self.df.columns]
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")
            
            # Strip any currency symbols and commas from Price
            self.df['Price'] = self.df['Price'].astype(str).str.replace('[$,KSh]', '', regex=True)
            
            # Force convert to numeric, replacing errors with NaN
            self.df['Price'] = pd.to_numeric(self.df['Price'], errors='coerce')
            self.df['Bedrooms'] = pd.to_numeric(self.df['Bedrooms'], errors='coerce')
            self.df['Bathrooms'] = pd.to_numeric(self.df['Bathrooms'], errors='coerce')
            
            print("\nData types after conversion:", self.df.dtypes)
            print("\nSummary statistics:")
            print(self.df[['Price', 'Bedrooms', 'Bathrooms']].describe())
            
            # Fill NaN values
            self.df['Price'] = self.df['Price'].fillna(self.df['Price'].median())
            self.df['Bedrooms'] = self.df['Bedrooms'].fillna(self.df['Bedrooms'].median())
            self.df['Bathrooms'] = self.df['Bathrooms'].fillna(self.df['Bathrooms'].median())
            
            # Prepare features
            features = self.df[['Price', 'Bedrooms', 'Bathrooms']].values
            self.scaler = StandardScaler()
            self.features_scaled = self.scaler.fit_transform(features)
            
        except Exception as e:
            print(f"Error in initialization: {str(e)}")
            raise

    def get_recommendations(self, location=None, price=None, bedrooms=None, bathrooms=None, num_recommendations=5):
        try:
            print(f"\nGetting recommendations with parameters:")
            print(f"Location: {location}")
            print(f"Price: {price}")
            print(f"Bedrooms: {bedrooms}")
            print(f"Bathrooms: {bathrooms}")
            
            # Convert inputs to float, using median if None
            try:
                price = float(price) if price is not None else float(self.df['Price'].median())
                bedrooms = float(bedrooms) if bedrooms is not None else float(self.df['Bedrooms'].median())
                bathrooms = float(bathrooms) if bathrooms is not None else float(self.df['Bathrooms'].median())
            except (ValueError, TypeError) as e:
                print(f"Error converting inputs: {str(e)}")
                price = float(self.df['Price'].median())
                bedrooms = float(self.df['Bedrooms'].median())
                bathrooms = float(self.df['Bathrooms'].median())
            
            print(f"\nProcessed parameters:")
            print(f"Price: {price}")
            print(f"Bedrooms: {bedrooms}")
            print(f"Bathrooms: {bathrooms}")
            
            # Create query point
            query = np.array([[price, bedrooms, bathrooms]], dtype=float)
            query_scaled = self.scaler.transform(query)
            
            # Calculate similarities
            similarities = cosine_similarity(query_scaled, self.features_scaled)
            similar_indices = similarities[0].argsort()[-num_recommendations:][::-1]
            
            # Get recommendations
            recommendations = []
            for idx, score in zip(similar_indices, similarities[0][similar_indices]):
                rec = {
                    'price': float(self.df.iloc[idx]['Price']),
                    'bedrooms': int(self.df.iloc[idx]['Bedrooms']),
                    'bathrooms': int(self.df.iloc[idx]['Bathrooms']),
                    'neighborhood': str(self.df.iloc[idx].get('Neighborhood', '')),
                    'agency': str(self.df.iloc[idx].get('Agency', 'Unknown')),  # Add agency field
                    'similarity_score': round(float(score) * 100, 2)
                }
                recommendations.append(rec)
            
            print(f"\nFound {len(recommendations)} recommendations")
            if recommendations:
                print("Sample recommendation:", recommendations[0])
            
            return recommendations
            
        except Exception as e:
            print(f"Error in get_recommendations: {str(e)}")
            print("Stack trace:", traceback.format_exc())
            return []

    def get_price_range(self, neighborhood):
        """Get price statistics for a neighborhood"""
        try:
            neighborhood_data = self.df[
                self.df['Neighborhood'].str.lower().str.contains(neighborhood.lower(), na=False)
            ]['Price']
            if not neighborhood_data.empty:
                return {
                    'min_price': float(neighborhood_data.min()),
                    'max_price': float(neighborhood_data.max()),
                    'avg_price': float(neighborhood_data.mean()),
                    'median_price': float(neighborhood_data.median())
                }
        except Exception:
            pass
        return None
